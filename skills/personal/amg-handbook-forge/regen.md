# Regen — regeneration / post-promotion runs ONLY (zero per-run tax)

1. **Triage, cheapest first**: grep `STALE:` markers → rows expired by `as_of` +
   header half-life → execution-state rows → dead/drifted links. Unexpired rows
   with clean SIFT-ledger entries are NOT re-verified.
2. **Mechanical checks, no LLM judgment**: run `scripts/verify_quotes.py` +
   `scripts/check_sources.py` on the bundle — HTTP 200 ≠ "still supports the
   claim"; a missing quote = content drift = treat as dead. Re-run
   execution-state rows verbatim; diff pinned versions against registries.
3. **Targeted re-research only for failures/expiries** (the round-1 loop: SIFT,
   tier bias, grounding check).
4. **Patch vs regenerate**: failed+expired < ~30% (default) AND no P0 taxonomy
   diff → patch in place; else the domain moved → full run. (The persisted
   taxonomy is the structural-change detector — reuse it, no new machinery.)
5. **Merge without clobbering**: 3-way — base = `.forge/pristine/<slug>/`, ours =
   human-edited promoted, theirs = new. Human-owned sections are skipped
   wholesale; conflicts go UNRESOLVED to the staging gate — never auto-pick.
6. **Delete-or-demote**: rows failing re-verification are deleted or demoted with
   a one-line `superseded:` reason; silent retention is a gate violation. Any
   execution-state row not re-confirmable now demotes to citation/candidate (one
   confidently-wrong command discredits the corpus).
7. **Do-not-resurrect (derived, not maintained)**: killed-row set =
   pristine-minus-promoted diff; never re-emit a human-killed claim without new
   primary evidence.
8. **CQ refresh (criteria drift)**: re-derive/extend the Acceptance CQs from the
   promotion diff BEFORE using them as the regen gate — frozen criteria are
   guaranteed to drift.
9. **Cross-run loop**: read the run log's per-block prose diagnoses; fix exactly
   ONE thing per round in the owning phase's instructions (not-delta → P3 · stale
   → P4 recency · wrong-lane/overlong → P5 lints · coverage-miss → P0/P2). Never
   revert a change on a single-run metric with <3 comparable runs.
10. **Output**: per-row diff changelog `{row, action, trigger: ttl | link-dead |
    drift | version | check-failed, evidence}` for the staging gate; refresh
    `.forge/pristine/<slug>/` after approval.

All numeric thresholds are calibration defaults (see cartography.md closing rule).
