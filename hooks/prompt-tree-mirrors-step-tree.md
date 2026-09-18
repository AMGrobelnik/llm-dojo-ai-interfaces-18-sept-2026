<!-- hook: prompt-tree-mirrors-step-tree -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# prompts/steps/_N_phase/_M_module dirs and steps/_N_phase/_M_module.py modules agree exactly, numbering included

The mirror holds everywhere today
(steps/_2_hypo_loop/{_1_gen_hypo,_2_review_hypo}.py ↔
prompts/steps/_2_hypo_loop/{_1_gen_hypo,_2_review_hypo}/; _3_invention_loop
_1.._6; _4_gen_paper_repo _2/_3/_4 — full listing verified; _1_gen_repo.py and
_5_deploy_gh.py are legitimately promptless non-LLM steps). The existing agent
rule module-registration-complete fires only on ADDED files (condition:
--diff-filter=A), so a rename/renumber that strands a prompt dir passes it
silently — and repo CLAUDE.md documents that near-miss directory names make
source-scanning guards silently stop seeing files. Check both directions:
every prompt dir has a matching step module; every step module importing
aii_pipeline.prompts.steps.X has dir X.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-pipeline)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/check_prompt_step_mirror.py

Delete-check: The real deletion is the one module-registration-complete's own delete-check
names: declare the pipeline shape once as data and derive both trees. Until
that exists, this cmd rule mechanizes the rename/renumber half the agent rule
cannot see.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Mechanical whole-tree mirror check that the agent-verified module-
registration-complete cannot guarantee (numbering drift, ghost dirs). Bridge
rule until the declare-shape-once-as-data deletion both delete-checks point at
exists.
- KEEP: Cheap directory-comparison check with two pinned promptless
exceptions; a mismatch means a step whose prompts silently never load. Fine as
a stopgap until the declare-shape-once-as-data deletion that module-
registration-complete's delete-check names.
- KEEP: Directory-listing comparison with a pinned promptless-step exception
list. Deterministic; a new module without its prompt dir (or vice versa) fails
loudly.
