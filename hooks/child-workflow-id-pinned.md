<!-- hook: child-workflow-id-pinned -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every DBOS.start_workflow_async call in aii_pipeline sits inside a `with SetWorkflowID(...)` block

22/22 current spawn sites comply (pipeline.py:162-166,413-428;
_invention_loop_iter.py:352-353,380-381,408-409,439-443,469,501;
_hypo_loop_iter.py:147-148,191-192; hypo_loop.py:146-147;
invention_loop.py:289-290; _2_gen_plan.py:311-312; _3_gen_art.py:517-518;
_2_gen_viz.py:490-491; _3_gen_demo_art.py:478-479; gen_paper_repo.py:195-196;
_cli/dispatch.py:420-428; _cli/_dispatch/_fresh.py:179).
steps/__init__.py:11-12 documents the convention ('under a deterministic
SetWorkflowID'). A bare call mints a random workflow_uuid: cancel-by-recompute
(pipeline.py:398-401 'recompute the same id on cancel without storing the
handles') and the FE chain-stitch that enumerates `<wid>-phase-...` ids
(aii_server/dashboard/api/run_events.py:162-165) silently miss that child, and
fork/resume id derivation breaks. Nothing mechanized guards the 23rd site;
rule-pipeline-workflow-contracts pins suffix parseability, not the pairing.

Mechanism (implemented 2026-08-26, `scripts/check_set_workflow_id.py`):

    .venv/bin/python $RULE_DIR/scripts/check_set_workflow_id.py

Arrives green, with **wider scope than proposed**. The rule named
`start_workflow_async` in `aii_pipeline`. Re-measured: spawns also happen in
`aii_server` (`run_stop.py`, `zombie_reaper.py`) and through three other DBOS
entry points. All 24 sites are compliant — 20 `start_workflow_async` and 1
`fork_workflow_async` in the pipeline, 2 `start_workflow_async` and 1
`start_workflow` in the server — so scoping to one package and one method
would have left the rest unguarded for no reason.

**`fork_workflow` appears 17 times and is called zero times.** Every mention
is prose in a docstring explaining the fork flow; the code calls
`fork_workflow_async`. A grep-based check would have counted all 17 and
reported a population that does not exist — the same prose-versus-code trap
`rule-prompt-tag-balance` and `rule-tsx-extension` each hit from a different
direction. The sync name is still listed, so adding a call later cannot slip
through.

Limit, stated rather than hidden: containment is LEXICAL. A spawn written
inside the `with` block but deferred — wrapped in a nested `def` that runs
later — reads as covered while executing outside the context manager.
Detecting that needs call-graph analysis; no such site exists, and the lexical
form is the one the convention is written in.

Probed seven ways: bare `start_workflow_async`, bare sync `start_workflow`,
bare `fork_workflow_async` and a spawn under a DIFFERENT context manager all
fire; `with` and `async with SetWorkflowID`, and a prose-only mention, do not.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-pipeline)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/check_set_workflow_id.py $(git ls-files 'aii_pipeline/src/**/*.py')

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- aii_pipeline | grep -q .`

Delete-check: Partially deletable: collapse spawn into one helper `spawn_child(workflow,
wf_input, wf_id)` that takes the id as a required argument, then ban bare
DBOS.start_workflow_async outright — the stronger end-state the rule should
prefer. Until that refactor, the AST pairing check pins the invariant.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: 22/22 comply and the failure mode (unpinned child id breaks DBOS
crash-recovery determinism) is silent until resume. Prefer the spawn_child(wf,
input, wf_id) helper collapse at adoption; fix-dbos-determinism does not cover
spawn-id pinning.
- KEEP: 22/22 comply and a miss breaks DBOS crash-recovery determinism
silently. Trivial AST check (start_workflow_async inside SetWorkflowID).
Consider implementing it inside the existing fix-dbos-determinism checker
rather than a new rule dir, but the invariant earns enforcement either way.
- KEEP: AST: every DBOS.start_workflow_async call node has a `with
SetWorkflowID` ancestor. 44 sites confirmed greppable today; deterministic and
loud.

## Overlap with restartable-workflow-id-one-door

Two hooks watch `SetWorkflowID` start sites, and the boundary between them is by
OWNERSHIP, decided semantically rather than by AST shape.

`restartable-workflow-id-one-door` owns a GOVERNED spawn under a
`with SetWorkflowID(id):` whose id is reused, persisted, or passed in — the
safety-net RESTART-under-a-possibly-terminal-row pattern
(`aii_server/dashboard/services/run_stop.py:110/124`, `zombie_reaper.py:271`),
whose failure mode is DBOS silently no-opping a start under an id whose row has
already reached SUCCESS: the dated 02:42 SUCCESS-row no-op incident documented
in `safety_net.py`. Those 25 sites are frozen in its `debt_setworkflowid.json`.

`child-workflow-id-pinned` (this hook) owns only FRESH child spawns — the id is
minted in the same scope (uuid4, or a parent id plus a suffix) — and requires
each to sit inside a `with SetWorkflowID(...)` block.

There is NO reliable AST discriminator between the two classes: both use
bare-Name and Call-form ids, both go through `start_workflow_async`, and both
include fire-and-forget spawns. The only difference is id PROVENANCE — can the
pinned id name a pre-existing, possibly terminal row — which is semantic, not
syntactic. This is why the mechanical carve-out between the hooks was dropped.

Today the two hooks' findings are DISJOINT and both empty (24 pinned child
spawns all compliant; restartable's 25 sites all grandfathered), so there is no
live double-bind — the conflict is LATENT. It surfaces only when someone adds a
genuinely new pinned child spawn, and it FAILS SAFE: restartable flags the new,
not-in-baseline `with SetWorkflowID(...)` site, and the resolution is a reviewed
edit to `debt_setworkflowid.json` — the same act all 25 current sites used.
`test_child_workflow_id_pinned_overlap_with_restartable.py` is the canary: it
goes red if a single `(path, line)` is ever flagged by BOTH hooks at once (the
real double-bind).

The eventual end-state is a shared one-door helper
`start_or_resume_under(wf_id, workflow, *args)` that both hooks would be
satisfied by. Building it is an owner-gated consumer refactor, and it also
requires lowering this hook's `_MIN_SPAWNS` floor (the spawns collapse into the
one helper), so it is not something either hook can do on its own.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
My own AST audit (scratchpad/spawn_audit.py, walks the enclosing `with`/`async
with` stack of every `*.start_workflow_async(` call across
aii_pipeline+aii_lib+aii_server) prints: "spawn sites: 22 / WITHOUT
SetWorkflowID: 0". So the 22/22 headline number is right and the invariant
genuinely holds — but it is not the same 22. My list includes
`aii_server/dashboard/api/run_stop.py:93` and `:105` (both `with
SetWorkflowID(wf_id): await DBOS.start_workflow_async(safety_net_*_workflow,
...)`), which t

Corrected statement of fact:
22 spawn sites and 0 bare is correct as a count, but the enumerated list is
not the live one: it invents `_fresh.py:179` as a spawn (it is a direct
`run_pipeline_workflow` call) and misses run_stop.py:93 and :105. The
cancel/recompute comment is at pipeline.py:385-389, not 398-401.
