<!-- hook: unset-key-one-default -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A config key whose value when UNSET is declared by more than one reader resolves to the same value in all of them — GET /config's inline fallbacks equal PipelineConfig's field defaults.

ADOPTION (2026-08-28): BUILT and clean. The two divergences recorded below
were measured BEFORE this gate existed and were fixed in `a66110996`
("GET /config defaults come from the models that own them");
`scripts/check_unset_defaults.py` exits 0 today over the nine fallbacks still
written as literals. The probe output that follows is the record of the
finding, not the current state.

Ran a probe walking PipelineConfig.model_fields for each dotted key in
`_projection.py`'s response dict (lines 310-338) and comparing against the
inline `.get(k, DEFAULT)` fallback. Output table:
`gen_hypo_loop.max_iterations 3 -> 2 <-- DIVERGES`;
`gen_hypo_loop.review_hypo.enabled False -> True <-- DIVERGES`; `diverging: 2`
(the other six — first_step, last_step, invention_loop.max_iterations,
gen_strat.art_limit, deploy_gh.enabled, viz_gen.image_model — agree).
Confirmed at source:
aii_pipeline/src/aii_pipeline/utils/config_models/invention_loop.py:95
`max_iterations: int = 2` and :87 `enabled: bool = True`. Canonical
pipeline.yaml currently supplies both (`gen_hypo_loop.max_iterations: 1` at
line 152, `review_hypo.enabled: true` at line 169) so the divergence is
latent, not live — the fallback only fires if canonical loses the key. The
repo already states this invariant elsewhere in its own words:
aii_config/dbos_run.yaml says of per_msg_summary "Values below mirror
PerMsgSummaryStepConfig's code defaults so this block is the operator knob
(omit it -> identical behaviour)", and aii_config/server/server.yaml:9-10 says
"The code default (settings.py) is debug=false — removing this key yields the
secure posture" (verified: settings.py:135 `DEBUG = _server.get("debug",
False)`).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: config-precedence)

Command (BUILT — `scripts/check_unset_defaults.py`), no condition —
whole-tree, runs unconditionally:

    .venv/bin/python $RULE_DIR/scripts/check_unset_defaults.py

**The two divergences this rule found are fixed** (`a66110996`): the projection
now reads `gen_hypo_loop.max_iterations` and `review_hypo.enabled` — and
`invention_loop.max_iterations` with them — from the models that declare them,
so those three cannot disagree by construction and the check skips them rather
than comparing a value against itself.

It compares the 9 fallbacks still written as literals, and all 9 agree today:
first_step, last_step, allowed_artifacts, art_limit, deploy_gh.enabled,
viz_gen.image_model, and the three compute floors.

**The gate carries its own population floor**, because every finding it can
report is produced inside a loop: if it resolves zero key paths through
`PipelineConfig` it exits 2 rather than reporting clean. That is
`rule-sweep-population-floor` applied to the checker enforcing this one —
verified by breaking the model walk, which produces "resolved 0 of 10" and
exit 2 instead of a green pass.

Verified to bite: restoring a literal that disagrees (99 against the model's 3)
fails naming both values.

Delete-check: Deletable and the rule should enforce the deleted end-state: give the
projection NO inline fallbacks — project from a validated `PipelineConfig` (or
from `PipelineConfig().model_dump()` as the base) so the model is the single
declaration of 'unset'. Then there is only one default per key and nothing to
keep in agreement.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
Wrote my own probe walking PipelineConfig.model_fields per dotted key and
comparing to the inline fallback literals I read out of
_projection.py:310-338: $ .venv/bin/python scratchpad/p2.py
init.pipeline.first_step code='hypo_loop' proj='hypo_loop' ok
init.pipeline.last_step code='gen_paper_repo' proj='gen_paper_repo' ok
gen_hypo_loop.max_iterations code=2 proj=3 DIVERGES
gen_hypo_loop.review_hypo.enabled code=True proj=False DIVERGES
invention_loop.max_iterations code=3 proj=3 ok
invention_loop.gen_strat.art_limit code=5 proj=5 ok
gen_paper_repo.deploy_gh.enabled code=True proj=True ok
gen_paper_repo.viz_gen.image_model code='flash' proj='flash' ok 2 of 8 diverge
— exactly the two the proposal names, exactly the values it names. Source
confirmed: $ grep -n 'max_iterations\|class '
aii_pipeline/src/aii_pipeline/utils/config_models/invention_loop.py 86:
enabled: bool = True (ReviewHypoConfig) 95: max_iterations: int = 2
(GenHypoLoopConfig) 199: max_iterations: int = 3 (InventionLoopConfig) LATENCY
confirmed — canonical supplies both (note the path is
aii_config/pipeline/pipeline.yaml, not aii_config/pipeline.yaml as the
proposal wrote it): $ grep -n 'max_iterations\|review_hypo:'
aii_config/pipeline/pipeline.yaml 152: max_iterations: 1 168: review_hypo:
169: enabled: true and frozen run snapshots carry them too
(aii_data/run_sgPjDucT_fId/config/pipeline.yaml:407,437). The fallbacks are
LIVE code, not dead: both callers pass a raw merged YAML dict, not a
model_dump — __init__.py:274 `resolve_config_response(cfg, ...)` where `cfg =
load_merged_pipeline_cfg(user_config_dir)`, and __init__.py:401
`resolve_config_response(snapshot, ...)`. So a user overlay or a snapshot
missing the key hits the wrong default. Supporting quotes verified verbatim: $
sed -n '7,12p' aii_config/server/server.yaml -> '# The code default
(settings.py) is debug=false — removing this key\n # yields the secure
posture.' $ grep -n 'debug' aii_server/config/settings.py -> 135:DEBUG =
_server.get("debug", False) (note: aii_server/config/settings.py, NOT
aii_server/dashboard/settings.py as the proposal wrote) $ grep -n 'mirror'
aii_config/dbos_run.yaml -> 52: '# result. Values below mirror
PerMsgSummaryStepConfig's code defaults' DEDUPE: nothing in claimed_r3.txt
covers agreement between a projection's inline fallbacks and the typed model's
field defaults. rule-deploy-config-single-source [ENFORCED] is deploy config
(server port); rule-publish-size-budget-single-source [PENDING] is size
ceilings. Different dimension.

Corrected statement of fact:
Two path typos in the why-text only, both harmless to the claim: the canonical
file is aii_config/pipeline/pipeline.yaml (line numbers 152/169 are correct
there), and DEBUG lives in aii_server/config/settings.py:135, not
aii_server/dashboard/settings.py.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Two independent readers declaring what a key means when unset is a
classic silent-divergence class — the dashboard shows one value, the run boots
another. Verified holds by execution, mechanically comparable (model_fields
defaults vs the projection's inline literals), and unclaimed by rule-config-
overlay-one-door or rule-lib-config-merge-paths.
- KEEP: Two implementations, both loud: compare projection fallback literals
against PipelineConfig.model_fields defaults by walking model_fields
(population generated), or enforce the delete-check end state that the
projection carries no inline fallbacks at all (clean ban). Distinct from the
overlay rules, which govern layering rather than the unset value.
- KEEP: Verified holds today, so it is a pure regression guard for a
divergence that arrives with the next added field — the deleted end state
(projection carries NO inline fallbacks, derived from a validated
PipelineConfig) is exactly what the rule pins, and it also subsumes the
absent-vs-empty candidate. Dedupe checked: I read ENFORCED rule-server-run-
config-api; it is a …


INVOCATION (corrected 2026-08-25): the command runs `.venv/bin/python`, not
bare `python3`. This checker imports `PipelineConfig` to read the model's
declared defaults, so it needs the repo's dependencies — and the engine builds
its own PATH (`_base_env` prepends the engine's `scripts/` dir) WITHOUT adding
`.venv/bin`, so `python3` resolves to the system interpreter.

It was authored as `python3` and tested with `.venv/bin/python`, so it passed
in testing and would have exited 2 — CANNOT_RUN — the moment it was approved.
That is the failure this rule family is named for: the result would have said
nothing while looking like a gate. Found by running every pending rule's
command under a replica of the engine's environment, which nothing else does;
`rule-pending-tree-approval-ready` checks metadata and the loader contract, not
whether a command can execute.

`rule-font-tokens/check.sh` and `rule-django-migrations/check.sh` are the house
precedent for naming the venv interpreter explicitly.