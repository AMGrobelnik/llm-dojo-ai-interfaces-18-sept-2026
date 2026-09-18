<!-- hook: module-workflow-rebinds-config -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every @DBOS.workflow whose input carries config_snapshot rebinds the ambient config before doing work

utils/context.py:21-23 states the invariant ('EVERY module / task workflow re-
binds them at entry') and context.py:24-31 + _phases.py:104-108 document the
silent failure: ContextVars do not cross start_workflow_async, so a workflow
that skips the rebind has prompt components read get_pipeline_config() is None
and quietly return '' (time_budgets.py:26-27 pattern) — prompts lose whole
sections and the human bubble never shows, with no error anywhere. The pattern
holds today only via convention: shared helpers do the rebind
(_rebuild_loop_ctx at _invention_loop_modules.py:122-130,
_rebuild_step_context at _phases.py:101-109, _hypo_loop_modules.py:60-68,
_gen_paper_repo_modules.py:173-181, pipeline.py:236). AST check: each
decorated workflow taking a config_snapshot-bearing input must call
set_pipeline_config or a helper that does (two-level call resolution).

Mechanism (implemented 2026-08-26, `scripts/check_ambient_rebind.py`):

    .venv/bin/python $RULE_DIR/scripts/check_ambient_rebind.py

Arrives green: 9 `@DBOS.workflow` functions carry a `config_snapshot`, 6 are
leaves, and all 6 rebind.

**The population is LEAF workflows, and missing that reports the orchestrators
as defects.** The other three — `run_pipeline_workflow`,
`hypo_loop_iter_workflow`, `invention_loop_iter_workflow` — spawn child
workflows and do no prompt work themselves, so they correctly do not rebind;
each child rebinds on entry. A first pass flagged all three as violations,
which is why the discriminator is spawning behaviour rather than the decorator
alone. That also matches how `context.py` words the convention — "every MODULE
/ TASK workflow re-binds" — because module and task workflows are exactly the
leaves.

Rebinding is resolved TWO LEVELS deep: the leaves rarely call
`set_pipeline_config` directly, they call a shared helper that does
(`_rebuild_loop_ctx`, `_rebuild_step_context` and siblings — 10 such helpers
exist). Requiring the direct call would flag every leaf in the tree.

Probed six ways: a leaf with no rebind fires; a leaf calling
`set_pipeline_config`, a leaf going through a helper, a spawning orchestrator,
an undecorated function and a workflow carrying no snapshot all do not.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-pipeline)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/check_ambient_rebind.py

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- aii_pipeline | grep -q .`

Delete-check: Cannot delete the dimension — ContextVar non-propagation across DBOS spawn
boundaries is inherent; the shared _rebuild_* helpers ARE the collapse
already. The rule verifies every qualifying workflow routes through one.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: ContextVar non-propagation across DBOS spawn is inherent and the
failure is silent (prompt components read defaults). Dimension cannot be
deleted; the check is the only closure.
- KEEP: ContextVar non-propagation across spawn is structural and the failure
is silent (stale config read as fresh). AST check: @DBOS.workflow taking
config_snapshot must call the rebind helper. Bounded scope, low FP, high
silent-failure value.
- KEEP: AST: @DBOS.workflow functions whose input schema carries
config_snapshot must call a _rebuild_*/rebind helper. Name-based heuristic is
stable (helpers already shared); missing rebind fails loudly.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Every quoted anchor checks out: utils/context.py states 'does NOT propagate
across DBOS ``start_workflow_async`` boundaries, so EVERY module / task
workflow re-binds them at entry by calling this' at lines 22-23 (invariant
spans 20-23, cited 21-23), with the human-bubble failure at 24-31;
_phases.py:104-108 is the 'prompt components would otherwise read
``get_pipeline_config() is None``' comment; time_budgets.py:25-27 and 58-60
are the quiet `return ""`. All five helper citations are exact (impo

Corrected statement of fact:
The invariant, its documentation, the five helper sites and the absence of any
gate are all as claimed. The check specified is not: 'two-level call
resolution' would raise 11 false positives today — 9 workflows that reach the
rebind at three hops, plus the 2 iter workflows that legitimately never bind
the ambient config. The rule needs unbounded (or >=3-level) intra-package call
resolution and an explicit carve-out for iter workflows, which the context.py
sentence ('EVERY module / task workflow') never covered.
