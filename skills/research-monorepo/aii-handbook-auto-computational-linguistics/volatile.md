# Volatile — aii-handbook-auto-computational-linguistics   (fact half-life ≈ 3 months)

The Frontier tier decays fastest. Re-verify the primary source before relying on any of these in a
novelty verdict or a write-up. `as_of` = the source's own date, not the date you read this.

## Lane-occupancy flags (novelty-critical — these read "open" to an unprimed searcher)

- **Contamination work has MOVED PAST detection.** ["we first highlight the wide prevalence of benchmark dataset contamination and outline the properties of contamination-resistant datasets"](https://arxiv.org/abs/2605.19999) — `as_of: 2026-05` · `applies-to: LLM benchmark design` · **ICML 2026 Position Track** — [S14].
  supersession: detection-method papers were the lane → the stated agenda is now resistance-by-design. re-verify: search "contamination-resistant benchmark <year>" before proposing a detector as novel.
- **Judge validity has been reframed as a SYSTEMS property, not a correlation.** ["Evaluation validity is not a property of a judge in isolation"](https://judge2026.github.io/) — `as_of: 2026` · `applies-to: LLM-as-judge in RLHF/DPO pipelines` — [S25]. A new judge-bias catalogue re-treads the prior framing.
- **Grammaticality-in-representations is OCCUPIED.** ["this simple grammaticality probe generalizes to human-curated grammaticality judgment benchmarks and outperforms LM probability-based grammaticality judgments"](https://arxiv.org/abs/2605.05197) — `as_of: 2026-05` — [S12]. Note the boundary in the same paper: on semantic plausibility ["the probe however performs worse than string probability"](https://arxiv.org/abs/2605.05197).
- **The reading-time predictor question is OCCUPIED at layer granularity.** ["the representations from early layers outperform surprisal in predicting early-pass measures such as first fixation and gaze duration"](https://arxiv.org/abs/2604.18712) — `as_of: 2026-04` · `applies-to: 5 languages, 2 eye-tracking corpora` — [S23].

## Point-in-time numbers (do not quote as current without re-fetching)

- ARR capacity: ["In this cycle, we received 17,087 total submissions, with a pool of only 1,424 qualified area chairs and 10,636 reviewers."](https://aclrollingreview.org/may26-cycle-letter) — `as_of: 2026-05 cycle` — [S1]. Changes every cycle; the policy response (["including options for limiting submissions for the first time in ACL's history"](https://aclrollingreview.org/may26-cycle-letter)) was still under consideration at capture.
- Benchmark-validity review scope: ["With a team of 29 expert reviewers, we conduct a systematic review of 445 LLM benchmarks from leading conferences in natural language processing and machine learning."](https://arxiv.org/abs/2511.04703) — `as_of: 2025-11` — [S2].
- Resource-density figure: ["118 languages (59%) have an average RDI of zero across the LRE Map and the Linguistic Data Consortium (LDC)"](https://arxiv.org/abs/2605.17442) — `as_of: 2026-05` · `applies-to: the 200 most-spoken languages in Ethnologue, LRE Map + LDC only` — [S5]. Catalogue-dependent by construction; re-verify against the catalogues named, not in general.
- Multilingual/edge survey scope: ["we survey 232 papers that tackle this problem across the language modelling pipeline, from data collection to development and deployment"](https://arxiv.org/abs/2604.21637) — `as_of: 2026-04` — [S20].
- Surprisal tipping point: ["about two billion training tokens"](https://arxiv.org/abs/2304.11389) — `as_of: 2023` · `applies-to: contemporary-capacity Transformer LMs, latency measures` — [S16]. Old enough that the exact figure should be re-checked against current model families before quoting.

## Peer-review status (this field's record is unusually strong — prefer the reviewed anchors)

- **PUBLISHED / peer-reviewed:** [S2] NeurIPS 2025 D&B · [S3] EMNLP 2023 · [S8] **ACL 2026 Best Paper** ·
  [S11] TACL 2024 · [S13] EMNLP 2025 · [S14] ICML 2026 Position Track · [S16] Findings of EMNLP 2023 ·
  [S17] EACL 2026 · [S18] CoNLL 2023 · [S21] ACL 2025 · [S23] ACL 2026. These decay slowly; lead with them.
- **arXiv preprints, NOT peer-reviewed** (`as_of` in the row): [S4] modal-models framing ·
  [S5] visibility asymmetry · [S6] perspectivist survey · [S7] Selbstzweck position ·
  [S19] DIALECTBENCH · [S20] edge-multilinguality survey · [S22] review-quality study ·
  [S24] discrete-reasoning barriers survey. Search for venue acceptance before citing any as settled.
- **Official venue/publisher artifacts** (stable but versioned): [S1] ARR cycle letter ·
  [S9] *Computational Linguistics* submission policy · [S10] + [S15] ACL 2026 pages (**one vote**,
  same origin) · [S25] JUDGe 2026 workshop page.

## Field-calendar items (stale within one cycle)

- ACL 2026's special theme was model explainability [S10]; the theme rotates annually. Re-check the
  current year's call before treating it as the field's standing emphasis.
- ARR cycle statistics [S1] and the ACL award slate [S15] are per-year artifacts. Re-fetch rather
  than quoting these across cycles.
