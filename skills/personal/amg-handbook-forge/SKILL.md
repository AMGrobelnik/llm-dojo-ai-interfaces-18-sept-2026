---
name: amg-handbook-forge
description: "Generates a new aii-handbook-auto-DOMAIN skill for a research field: maps the field, mines real sources for its recent frontier, already-crowded lanes, shaky assumptions and expert-vs-novice gotchas, verifies every claim against a quoted URL, then A/B-gates the draft against a no-handbook baseline and stages it for a human to promote. Use whenever a request asks to bootstrap, scaffold, forge or auto-generate a domain, topic or field handbook or starter skill, to capture what an expert knows about a field, or to build a what-Claude-should-know-in-domain-X guide, even phrased loosely as make a handbook for X. Triggers: handbook forge, domain or field handbook, expert knowledge capture, field pitfalls, recency map, crowded lanes, delta gate. NOT for: reading or applying an already-generated aii-handbook-auto handbook, authoring or evaluating a general-purpose skill (use anthropic-skill-creator), one-off domain questions, or documenting this repo's own code."
---

# Handbook Forge

Auto-generate a compact, verified **handbook skill**: the non-obvious, high-leverage knowledge
an expert carries, distilled small, as a **draft** a human then refines. The reader of the handbook
is an LLM doing the domain's real work — for research domains, the whole lifecycle: come up with
hypotheses and judge their novelty → design studies and experiments → write up results.

The output is always **staged** in `handbook-staging/` for human review — never auto-loaded into the pipeline.

## What matters most — read this first

These four rules decide whether the run is worth anything:

- **You are a knowledge engineer mining real sources, not an expert writing from memory — memory is
  net-negative by default.** An LLM playing "expert" just restates what the base model already knows.
  The value is the loop the model can't fake: **map the field → mine real artifacts → contrast
  expert-vs-novice choices → verify every claim** — external grounding, pruning of what the model already
  knows, and the human review gate. Spend effort on fetched artifacts, not self-written prose (and don't
  build a tower of self-checks — verifiers from the same model family share the same blind spots).
- **Creation cost is not a constraint.** This is a one-time, high-impact setup, and the handbook is what
  separates groundbreaking pipeline output from incremental. Spare no effort where it helps — deep mining,
  many parallel subagents, exhaustive verification. But effort should buy *grounded material*, not more prose,
  and the finished handbook stays compact.
- **Inform broadly; never prescribe (the anti-tunnel-vision rule).** The model already generates ideas well.
  Hand it a specific idea, mechanism, or recipe and it just elaborates *your* idea (tunnel vision) — and it's
  redundant anyway. So give **material** (the field's current state, what's already crowded, the open tensions),
  never **conclusions**. Any line that reads "do X" → rewrite it as the observation behind X. (We tested this:
  prescriptive handbooks overfit to one flavor of idea; facts + open questions generalize.)
- **The run can fail, and that's fine.** Phase P6 measures whether the handbook actually improves behavior.
  If it doesn't, the honest result is to ship nothing.

## What goes in the handbook — words in proportion to value

"Value" here means: **what a current expert in the field knows that the base model + a generic research
prompt do NOT.** Rank everything by that. It comes in two layers, plus a floor:

- **Layer 1 — Situational awareness (the SUBSTRATE). Rank this first — it's the most reliable value.**
  The recent state of the field that isn't in the model's training data — what it would otherwise have to
  re-derive by searching on every run. Pre-curated, grounded in sources, and marked for what's already
  crowded ("don't redo this").
- **Layer 2 — The lens (kept deliberately broad).** At most, a set of **open questions** the reader answers
  on their own (shaky assumptions, unexplained anomalies, gaps), plus an explicit "these areas are crowded,
  go elsewhere" list. Never a prescribed direction.
- **The floor — correct execution.** For each: a naive move → the expert move that replaces it. If it's
  something a weaker/other/future model might get wrong but strong models know, keep one terse line. If it's
  universal or already enforced by the toolchain, drop it.

## The method — eight phases, run in order (P0 → P7)

**P0-P7 are the eight sequential phases of building one handbook.** Do them in order; each builds on the last.
Work inline by default, but spawn subagents freely wherever they clearly help. Every subagent writes its findings to a named file under `.forge/` as its *first*
action, so nothing is lost if it dies and a resumer can pick up where it left off. Only one agent writes to the
handbook bundle at a time.

### P0 — Charter + map the field
Read `cartography.md` first — every P0 recipe lives there. Produce one
saved "map" of the field, plus:
- **Charter card:** purpose; what's in and out of scope; the **consumer persona** (the base LLM + its tools +
  its version window — usually a full research agent, never an "expert persona"); constraints.
- **3-7 motivating scenarios** spanning the pipeline's real stages. The *same* scenarios become the baseline
  in P1 and the A/B test in P6.
- **Bootstrap the field's structure:** read a few top-level surveys/overviews, diff their taxonomies, and note
  each subarea's type (empirical / normative / craft).
- **Borrow the settled canon** from the newest good survey, so the handbook doesn't re-teach what's already known.
- **Set up source trust:** find the field's own reliability ladder if one exists; do one "lateral read" per
  recurring source and remember the verdict.
- **Comprehension questions (≤25):** used later to *test* coverage, never to generate content.
- **Build the recency map (the SUBSTRATE):** organizing principles + a recency-weighted frontier (newest first,
  dated, one insight per work). Ship only the most-recurring / load-bearing claims; the mined long tail stays
  in the `.forge/` files, unshipped — fine-grained depth measurably anchors ideation, so no depth annexes.
  Tag what's now crowded (don't-redo).
- **Draft the lens as open questions:** from shaky assumptions, important-and-now-tractable problems, dead ends,
  and the field's sense of what "deep" means — but emit them as *questions the reader answers alone*, never as directions.

### P1 — Baseline (what to measure the handbook against)
The handbook only has value if it beats what the **real consumer already does without it** — and the real
consumer keeps all its tools and other skills. So there is **one** baseline: **the actual pipeline agent, with
full tool access (web search, etc.) and every other skill, minus only the handbook.** Run the P0 scenarios on it.
- What it already produces, or can find by searching → NOT handbook material (it gets there on its own).
- What it misses, gets wrong, or gets stale even with tools → the handbook's candidate value, and your mining agenda.
- **GO/NO-GO gate — forge SELECTIVELY.** Read the baseline's ceiling-scenario output for how much of the
  handbook's intended job it already does unaided. If it already reaches the ceiling, forge MINIMALLY or skip;
  concentrate the (unbounded) forge effort on fields where it demonstrably underperforms.
  **Judgment call, not a measurement — corrected 2026-07-29.** This gate used to cite a measured result ("a
  field whose baseline searches the open lanes well yields a handbook that only TIES") and to tell you to score
  the baseline "the way P6 will … best-of". Both halves are gone: best-of picks are pseudo-replication, and on
  the one valid (idea-level) analysis no handbook beat or lost to its baseline significantly in any field. So
  the gate keeps its DIRECTION — spend forge effort where the baseline is weakest — while losing its evidence.
  Treat it as a cheap prior for allocating effort, and never as a demonstrated delta.

The handbook's honest delta is curation + grounding + don't-redo + framing — saving the agent from re-deriving
the same thing every run — **not** "the model couldn't have known." P3 and P6 both compare against this same baseline.

### P2 — Harvest (mine the real sources)
- The map's core segments set each miner's **scope**; the source types (see Sources below) set what to search
  **within** that scope. Skip source types that don't exist for a given scope.
- Coverage rule: every line on the map is either mined or explicitly marked "no added value."
- Every candidate finding comes back with a **required grounding quote + URL**.
- **Harvest write-as-you-go, and keep verification separate.** Write each claim the moment you have it (roughly
  one fetch → one claim), never batch at the very end. Prefer **stable abstract-level quotes** (a sentence from
  the paper's abstract / landing page — reliably grep-verifiable) over reflowed body or PDF text.
  **A summarizing fetch is a LEAD, never a quote source** — any string that will ship between quote marks must
  come from the RAW extractor output (the same one `verify_quotes.py` reads), never from a model's rendering of
  the page, even when it was asked for verbatim text and reports that it complied (measured 2026-07: 2/106 quotes
  were silently altered this way — a contraction inserted, and a cut straight through inline LaTeX — and that was
  100% of the run's citation defects; both were invisible to reading). Do NOT
  verify-as-you-mine: that traps miners in endless re-fetching. Verification is P4's job; a bounded fetch budget
  (~1 fetch per claim) keeps a miner from stalling with a huge transcript and nothing written.

### P3 — Rank by value (the single most important phase)
Decide what's worth keeping by *probing behavior*, not by what feels obvious:
- Where the P1 baseline already covers a finding, compare against it. Otherwise probe: give a fresh
  **tool-equipped** subagent (web + skills, but not the handbook) the scenario, with questions that never hint
  at the candidate answer, and judge by what it produces on its own.
- Judge by the probe's actual output:
  - confidently stale / deprecated → **keep, at the top of the floor** (highest correction value);
  - matches current reality → one known-lane line (drop only if universal);
  - wrong / missing → a full value row.
- **Contrast rows** = the expert choice vs the plausible-novice choice, plus the cue that tells them apart.
- Ranking order: **substrate first** (recency/frontier + what's crowded), then the **lens** (shaky assumption >
  important open problem > taste cue > dead end), then the floor by impact.
- **Re-verify every "crowded" tag — and hunt for the lanes you did NOT list — with a fresh, dated saturation
  search before it ships.** A *missing* crowded-lane is the delta-gate's #1 failure mode (measured): it lets the
  consumer propose an already-preempted idea believing the space is blank — the exact way a compact handbook loses
  to a tool-equipped baseline that was forced to search. An "open / no prior work" implication with no fetched,
  dated saturation check is not yet earned. **Default any UNCHECKED lane to OCCUPIED** (measured 2026-07: **11/11** —
  every lane shipped as "plausibly occupied, not saturation-checked this pass" came back occupied on a later
  dated sweep, most with a dedicated survey, workshop series, or shared task). So a candidate-lane entry that admits an unchecked
  lane is a work item to CLOSE before ship, not an acceptable shipping state.

### P4 — Verify (every claim, against a source)
- One grounding check per claim: the exact quote **literally appears** in the source (`scripts/verify_quotes.py`)
  AND that quote actually **supports** the claim (not just shares its topic). A true claim with a fake citation
  is worse than no citation.
- Run one batched adversarial review in a context *separate* from the writer, to catch what the mechanical check can't.
- Then loop `scripts/verify_quotes.py` + `scripts/check_sources.py`, fixing each miss (fix the quote, fix the URL,
  or demote it to the candidate lane) until **both exit 0 with zero problems**. A failing verifier blocks the run.

### P5 — Compose (write the handbook)
- Fill in `output-template.md` — **read it now; all the formatting rules live there.** Order is substrate → lens
  → floor; volatile facts go to `volatile.md`; everything below the centrality bar stays in `.forge/`, unshipped.
- **Per-segment check:** a fresh subagent should be able to answer that segment's questions from that segment's
  text alone. If it can't, mine more before writing.

### P6 — Delta gate (does it actually help?)
This is the falsification step — the run's pass/fail.
- A fresh consumer agent runs the P0 scenarios **with** the handbook; compare against the P1 baseline —
  identical except the handbook is removed.
- **Sample k≥6 ideations per arm, not one** — a single draw is draw-noise (measured across two fields: an
  n=1 "clean win" and an n=1 "near-tie" both collapsed to the same modest, non-significant reality at k=6).
  Blind-pool + shuffle all 2k outputs, judge with **≥3 independent checkers** on bounded yes/no criteria;
  agreement is your reliability meter (disagreement → human review). Criteria check both layers: does it engage
  the current frontier and avoid crowded lanes better than the baseline? does it target a mapped important
  problem and challenge a mapped assumption, rather than just fill a gap?
- **Score by IDEA, and by nothing else — corrected 2026-07-29, and this bullet used to say the opposite.**
  Each generated idea is one independent draw; score it by the fraction of checkers voting yes and compare
  the two arms' distributions with an exact Mann-Whitney U. Do **NOT** tally best-of picks (all checkers judge
  the SAME pool, so they are many reads of one draw — pseudo-replication) and do **NOT** run Fisher on raw
  votes (N checkers × k ideas is clustered, not N×k observations). Both were previously the primary read-out,
  and every arm-vs-arm verdict taken on them is retracted: *"this forge has never demonstrated a
  statistically significant ideation benefit from any handbook — in either direction"* (`measurements.md`).
- **Power comes from ROUNDS — not checkers, not k.** At 2 rounds × 12 ideas the design cannot detect a +0.09
  effect, so a k=12 gate is not a small version of a decisive study, it is an undecidable one. Testing the one
  live hypothesis (`challenges_assumption`, +0.08/+0.04/+0.10/+0.15, pooled p=0.063) needs ~8–10 rounds per
  arm. **Do not spend on another 2-round gate, and do not buy power with checkers** — a 16-checker top-up over
  existing pools cost ~4.4M tokens and could not move the result even in principle.
- **Use the hardened harness: `scripts/delta_gate.template.js` + `scripts/analyze_p6.py`.** Fill the
  three constants at the top of the template (never pass them through a parameter channel) — it
  throws before spawning if any is empty, and aborts the run if a handbook-arm agent reports
  `HANDBOOK_MISSING`. Both guards exist because a run that lost its parameters once produced a
  complete, clean-looking verdict over a pool where both arms were identical (28 agents, ~1.3M
  tokens, zero validity). `analyze_p6.py` re-checks both guards, derives the arm key independently
  of the one the workflow returns, and prints picks → votes → rate in that order.
  **Its print order is the RETRACTED order and the script has not been updated** — picks and votes are
  pseudo-replication (above), so read its output for the guards and the raw per-idea scores, then do the
  idea-level Mann-Whitney yourself. Treat the three headline numbers it prints as decoration.
- **Before computing anything, spot-read the returned IDEAS for on-domain-ness.** Summary statistics
  cannot reveal that both arms answered the wrong question; that is what caught the run above.
- The worked runs behind every "(measured)" claim here and in P1 — density anchors (the best-supported one),
  n=1 overstates magnitude, and the retraction that killed best-of-not-mean — are recorded in
  `measurements.md` (distilled; raw harness in `.forge/`). **Read its header before citing any number from
  this file as measured:** most of this spec's "(measured)" claims predate 2026-07-29 and rest on units that
  analysis retracted. They mostly still stand as directional priors with a named mechanism; none of them
  stands as a significance claim.
- **Plus a human verdict on genuine novelty — never an LLM preference judge.**
- Outcomes: no change → compress that block to one line (cut only if universal); a recurring un-fixed error →
  a missing block to add; worse than baseline → don't ship that block (or ship nothing).

### P7 — Trigger + handoff
- Hand the trigger-wording tuning to `anthropic-skill-creator` (don't rebuild that tooling here).
- Log each block's P6 verdict + a one-line why, and note which sources / candidate items the human refiner
  confirmed or killed — that human edit *is* the expert knowledge being captured.
- Re-generating the handbook later → follow `regen.md`.

## Sources — a search bias, not a rigid ranking

Rank a source by how much it **reveals** real expert behavior vs just **narrates** it, weighted by how easily a
tool can reach it. Gate cheaply: one memoized "lateral read" per recurring
source/author/venue — criteria, verdict rubric, and dating rules in `credibility.md`. Some claim types flip the ranking — for a "this is settled" or "this is a known gap" claim, the
survey/roadmap that maps the whole line outranks the newest preprint riding it.

The tiers, best-revealing first:
- **A — Executable / behavioral artifacts** (the ground truth: tests, diffs, PR *rejections*, non-default config
  values, ADRs). Favor the reachable ones first: changelogs, release notes (`BREAKING`/`deprecated`), closed
  `wontfix`/`by-design` issues, migration guides.
- **B — Incident narratives** (postmortems/RCAs, "lessons learned", "why we moved off X", high-reaction bug
  threads, RFC/ADR debates, accepted-answer corrections).
- **L — Landscape & ceiling syntheses** (surveys/roadmaps — especially their *open-problems / future-directions /
  limitations* sections; critiques, replication failures, retrospectives, negative results, position papers;
  best-paper/award rationales and "what makes a great X paper" essays; the work that *defined* a line). This is
  the main source for the ideation lens (open problems, shaky assumptions, taste, dead ends).
- **C — Opinionated distillations** (gotchas/footguns/pitfalls; `awesome-<X>` lists as a link frontier, never
  quoted). These are leads to verify, never final content.
- **D — Self-report / canon** (official overviews, intro tutorials, "N tips" listicles). This is the base-model
  exclusion set: subtract it or compress to one known-lane line, never payload.
- **E — Forbidden as evidence:** an LLM's "expert persona" introspection, your own reasoning, or any other
  model's free text dressed up as human expertise.

Rule of thumb: mine the **corrections layer**, not the textbook — changelogs/deprecations for execution;
retrospectives / negative results / "we were wrong" for the ceiling. Prefer grounded over synthetic, and treat
several pages that copy each other as one vote. Persistence and stop-rules: `cartography.md`.

Useful negative-space searches: `label:wontfix|by-design sort:reactions-desc`; `"<domain>" (gotchas OR footguns
OR pitfalls OR "considered harmful")`; `"why we moved off <X>"`; `<domain> survey "open problems"|"future
directions"`; `<domain> "negative results" OR retrospective OR "we were wrong"`. More in `mining-annex.md`.

## Verification — external grounding is the whole point; everything else is motion

- **One grounding check per claim — the P4 rule.** If the quote clearly supports the claim but grep misses it
  (JS-rendered or reflowed page), move it to the candidate lane — don't drop it.
- **Three states a claim can ship in:**
  1. verified by execution (ran it, it passed);
  2. verified by citation (one faithful primary source — this ships);
  3. candidate ⚠️ (important but weak/no evidence — ships ONLY in the clearly-labelled candidate lane, never as
     normal content). Two independent sources raise confidence; two pages of shared origin count as one.
- Never lose a claim to verification failure alone: high-value-but-unverified ships in the candidate lane ⚠️;
  below-the-bar claims stay in the `.forge/` mining files, unshipped, whether verified or not.
- **Numbers** (limits, percentages, version thresholds, durations) must trace to a structured/primary source,
  never to LLM-summarized prose.
- **Recency is per-claim:** stamp volatile claims with `as_of` + the version they apply to; never self-certify
  that something is current — require a fetched, dated source.

## Output & staging (safety)

- Name it `aii-handbook-auto-<slug>` (`-auto-` = machine-generated; `aii-` means the pipeline will load it once
  a human promotes it).
- **Stage it outside `.claude/skills/`**, in `handbook-staging/aii-handbook-auto-<slug>/` (which is gitignored).
  A draft placed directly under `.claude/skills/aii-*` would auto-load and could ship unreviewed.
- Keep a copy of exactly what was generated (in `.forge/pristine/<slug>/`), so a human can later see what they changed.
- Finish by printing, for the human: how many unverified candidate (⚠️) items remain, the source count, the P6
  verdict (including "ship nothing" if that's the call), and the one-line command to promote it:
  `mv handbook-staging/aii-handbook-auto-<slug> .claude/skills/` — promoting is the human's decision, never automatic.
