# Volatile — aii-handbook-auto-neurosymbolic   (fact half-life ≈ months)

The Frontier tier of the map is inherently dated; these decay fastest — re-verify the primary
source before relying on any in a novelty verdict or write-up. `as_of` = the source's date.

## Wedge-occupancy (novelty-critical — these were "open" to the baseline, now partly taken)
- **Gold-free autoformalization certification is OCCUPIED.** ["We propose a roundtrip verification approach which does not require ground-truth annotations: formalize a statement, translate the result back to natural language, re-formalize, and use a formal tool to check logical equivalence."](https://arxiv.org/abs/2604.25031) — `as_of: 2026-04` · `applies-to: autoformalization / SMT-checkable statements` — [S9].
  supersession: was treated as an open wedge by the tool-only baseline → now published. re-verify: search "gold-free / roundtrip autoformalization faithfulness <year>" before claiming it open.
- **Ontology-as-faithfulness-lever is PARTLY OCCUPIED.** peer-reviewed evidence that NL-term embeddings collide with formal ontology syntax so models ["produce syntactic errors or hallucinate non-existent terms due to conflicting embeddings learned during base training"](https://proceedings.mlr.press/v284/thompson25a.html) — `as_of: 2025` · `applies-to: SUMO/SUO-KIF-style upper ontologies` — [S18].
  supersession: baseline assumed ontology grounding was a clean, blank lever → the failure mode is now documented (peer-reviewed). re-verify before framing ontology grounding as an unexplored faithfulness lever.

## Peer-review status of load-bearing preprints (re-check for published versions)
- **[S5] Know Your Limits — COLM-2026 under review** (`as_of: 2026-06`); load-bearing for accuracy≠faithfulness. Prefer the published version once it appears.
- **[S6] Do LLMs Game Formalization — arXiv preprint** (`as_of: 2026-04`); load-bearing correction of the "gaming" read. re-verify: search for a venue acceptance.
- **[S7] The Faithfulness Gap — arXiv preprint, 2-author, quality-flagged** (`as_of: 2026-06`); terminology/lead only, NOT load-bearing. Do not promote without corroboration.
- **[S18] Grounding Terms from an Ontology — PUBLISHED (NeSy 2025, PMLR v284)** (`as_of: 2025`); the peer-reviewed anchor — stable, decays slowly.

## Benchmark-validity numbers (point-in-time; the corrected splits are the moving target)
- FOLIO/MALLS carry ["approximately 39% and 36% of entries, respectively, contain incorrect FOL formalizations (i.e., ground truth labels)"](https://arxiv.org/abs/2606.02837); correcting them swings model accuracy +9–22pp — `as_of: 2026-06` · `applies-to: FOLIO + MALLS original labels` — [S13].
  supersession: the paper ships corrected labels + a relabeling framework; re-verify which split (original vs corrected) any leaderboard used before comparing to it.

## Frontier SOTA deltas — single in-house evals, treat as hypotheses
- SymCode ["up to 13.6 percentage points over baselines"](https://arxiv.org/abs/2510.25975) (`as_of: 2025-10`, single-paper eval — [S11]); fine-tuned Flan-T5-XXL ["70% accuracy with predicate lists, outperforming GPT-4o"](https://arxiv.org/abs/2509.22338) (`as_of: 2025-09` — [S8]); AlphaGeometry2 ["solving rate of AG to 84%"](https://arxiv.org/abs/2502.03544) (`as_of: 2025-02` — [S31]). Each is one lab's eval on its own setting — re-verify before quoting as SOTA.
