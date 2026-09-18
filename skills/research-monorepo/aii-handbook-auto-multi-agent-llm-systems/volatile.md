# Volatile — aii-handbook-auto-multi-agent-llm-systems   (fact half-life ≈ months)

- MAST figures: taxonomy from 150 traces (kappa = 0.88), 14 modes / 3 categories; MAST-Data = 1600+
  annotated traces across 7 frameworks — `as_of: 2025-10` · `applies-to: arXiv 2503.13657 v3` — [S1]
  supersession: commonly misrecalled as "~200 traces" → correct split is 150 (taxonomy dev) + 1600+
  (released dataset). re-verify: arxiv.org/abs/2503.13657 latest version.
- Best automated failure-attribution accuracy: 53.5% (Who&When) — `as_of: 2025-06` ·
  `applies-to: arXiv 2505.00212 v3` — [S12]
  supersession: a dense 2026 follow-on wave targets this number; treat it as a moving floor.
  re-verify: search Who&When follow-ups / attribution results newer than 2025-06.
- MAS cost anchors: ~15× chat tokens; token usage ≈ 80% of performance variance — `as_of: 2025-06` ·
  `applies-to: Anthropic's own research system (BrowseComp eval)` — [S3]
  vendor-internal and single-origin; corroborate independently (e.g. [S21]) before load-bearing use.
  re-verify: anthropic.com/engineering/multi-agent-research-system.
- Independent cost-accuracy Pareto: reflexive F1 0.943 at 2.3× cost; hierarchical supervisor-worker F1
  0.921 at 1.4× (frontier) — `as_of: 2026-03` · `applies-to: financial-document extraction, 4 patterns ×
  5 LLMs` — [S21]
  re-verify: whether a broader-domain replication exists before generalizing beyond document extraction.
- Adaptive-topology claim: +12–23% over static single-topology at identical models — `as_of: 2026-02` ·
  `applies-to: single-author preprint, unreviewed` — [S10]
  clashes with the overfitting/illusory-coordination result [S9]; see SKILL.md Open questions Q3.
  re-verify: peer-review status and any independent replication of either side.
- MoA headline: 65.1% vs 57.5% (GPT-4 Omni) — `as_of: 2024-06` · `applies-to: AlpacaEval 2.0, open-source
  pool` — [S22]
  re-verify: AlpacaEval has known length/style sensitivities; check the current leaderboard regime.
- Protocol scopes: MCP = model↔tools/data (2024-11); A2A = agent↔agent, complementary (2025-04) —
  `as_of: 2025-04` · `applies-to: the original announcements` — [S4] [S5]
  re-verify: governance and any scope merge/supersession of either protocol before citing the split.
- The crowded-lane list (SKILL.md "Already crowded"): compute-matched critique, adaptive topology + its
  rebuttal, failure attribution, latent comms, self-evolving MAS, new interop protocols — `as_of: 2026-07`
  · `applies-to: H2-2025 → H1-2026 literature scan` — [S6] [S8] [S9] [S10] [S12] [S17] [S14] [S4] [S5]
  supersession: lanes saturate and open within months in this field. re-verify: full re-scan at regen.
