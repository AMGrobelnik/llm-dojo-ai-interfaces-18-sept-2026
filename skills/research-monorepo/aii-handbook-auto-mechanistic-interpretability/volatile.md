# Volatile — aii-handbook-auto-mechanistic-interpretability   (fact half-life ≈ 3 months)

The Frontier tier decays fastest. Re-verify the primary source before relying on any of these in a
novelty verdict or a write-up. `as_of` = the source's own date, not the date you read this.

## Lane-occupancy flags (novelty-critical — these read "open" to an unprimed searcher)

- **Per-weight global interpretation is now OCCUPIED (thinly).** ["whether a single weight can be understood globally across the full training distribution"](https://arxiv.org/abs/2607.02964) — `as_of: 2026-07` · `applies-to: weight-sparse + dense transformers, 4 models` — [S2].
  supersession: behavior-scoped circuit finding was the only framing → a global per-parameter framing now exists. re-verify: search "per-weight / global weight interpretation transformer <year>" before claiming it open.
- **The AxBench "SAEs are not competitive" verdict is CONTESTED, not settled.** ["Sparse Autoencoders can, in fact, perform close to on par with the reference LoRA performance on the AxBench benchmark, when features are selected and labelled with our supervised pipeline"](https://arxiv.org/abs/2605.31183) — `as_of: 2026-05` · `applies-to: AxBench steering, supervised feature-selection pipelines` — [S25]. Unreviewed preprint; the raw-latent loss still stands.
- **Attribution-patching unreliability is DIAGNOSED AND FIXED in-paper.** ["the dominant error stems from the non-linearities in the downstream network rather than local curvature at the patched component"](https://arxiv.org/abs/2606.09899) — `as_of: 2026-06` — [S19]. Proposing "attribution patching may be unreliable" as a finding re-treads this.

## Point-in-time numbers (do not quote as current without re-fetching)

- Attribution graphs give satisfying insight on ["a quarter of the prompts we've tried"](https://transformer-circuits.pub/2025/attribution-graphs/biology.html) — `as_of: 2025-03` · `applies-to: Claude 3.5 Haiku + that replacement model` — [S11].
- Knowledge–action gap: ["SAE feature steering produced zero effect despite 3,695 significant features."](https://arxiv.org/abs/2603.18353) — `as_of: 2026-03` · `applies-to: Qwen 2.5 7B Instruct + Steerling-8B, clinical triage vignettes` — [S3]. One domain; treat as a strong existence proof, not a rate.
- Weight-sparse interpretability ceiling: ["scaling sparse models beyond tens of millions of nonzero parameters while preserving interpretability remains a challenge"](https://arxiv.org/abs/2511.13653) — `as_of: 2025-11` — [S18]. re-verify: this is the number most likely to have moved.
- MIB leaderboard verdict: ["the supervised DAS method performs best, while SAE features are not better than neurons, i.e., non-featurized hidden vectors"](https://arxiv.org/abs/2504.13151) — `as_of: 2025-04` · `applies-to: MIB causal-variable track` — [S10]. The leaderboard is explicitly still open [S22], so this ordering can change.

## Peer-review status of load-bearing preprints (re-check for published versions)

- **[S5] Non-Linear Representation Dilemma — PUBLISHED (NeurIPS 2025 Spotlight)** (`as_of: 2025-11`). The most stable anchor here; decays slowly.
- **[S10] MIB — PUBLISHED (ICML 2025, PMLR v267)**; **[S22] BlackboxNLP 2025 — PUBLISHED (proceedings)**.
- **[S3] Interpretability without actionability — arXiv preprint** (`as_of: 2026-03`); load-bearing for the knowledge-action gap. Search for a venue acceptance before citing as established.
- **[S4] Variance analysis · [S23] Many Circuits, One Mechanism · [S19] When Attribution Patching Lies — arXiv preprints** (`as_of: 2025-10 / 2026-06 / 2026-06`); jointly load-bearing for the stability critique. Prefer published versions once they appear.
- **[S25] SAE steering rebuttal · [S20] Steering-vector unreliability — unreviewed preprints, one/two authors.** Cite as contested positions, never as settled results.
- **[S6] lab-team post · [S7] editorial critique · [S15] CEO essay — none peer-reviewed.** These are evidence of stated positions and decisions, not of technical facts.

## Field-calendar items (stale within one cycle)

- ICML 2026 Mechanistic Interpretability Workshop is the venue whose stated bar is quoted in the
  taste section [S14] — `as_of: 2026`. Re-check the current year's CFP before treating the wording
  as the field's standing norm.
