<!-- hook: dbos-list-metadata-only -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# DBOS.list_workflows calls that consume only metadata pass load_input=False, load_output=False

Verified against the installed dbos: list_workflows defaults are
load_input=True, load_output=True (each row then deserializes the full
workflow input — the pipeline config snapshot). Eleven of twelve server call
sites pass the flags explicitly (api/__init__.py:273,513,560;
run_resume.py:140,157; redeploy_resume.py:74-79,485,504; safety_net.py:368;
signals.py:109-116; pod_discovery.py:226-232; zombie_reaper.py:229-234;
run_cancel.py:68-72,116-120). The single outlier is run_cost.py:366
(_workflow_statuses_for), which consumes ONLY workflow_id and status yet loads
full input+output blobs on every cost-status poll. The pattern is clearly
deliberate and one drift already exists.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-server)

Mechanism (implemented 2026-08-26, `scripts/check_list_workflow_loads.py`):

    .venv/bin/python $RULE_DIR/scripts/check_list_workflow_loads.py

**The gate is EXPLICITNESS, not a fixed value.** Loading the input is
sometimes right: `_cli/dispatch.py:166` passes `load_input=True` because it
starts a sibling workflow from the parent's input, and says so on the line.
Demanding False everywhere would either break that call or spend a waiver on
correct code. What no site should do is inherit the default silently, so both
flags must APPEAR — a True is then a decision on the record.

**Both stale counts are superseded; the whole-tree figure is 26.** The body
says "eleven of twelve", the 2026-08-22 verification says 19 — both counted
`aii_server` only. Across every tracked package there are **26** call sites,
including `list_workflows_async` in `aii_pipeline` and `aii_launcher`.

The outlier both counts named is FIXED: `run_cost.py` now passes both flags
with a comment, at :486 rather than the :366 or :369 previously cited. The
defect this arrives on instead was outside the scope either count used —
`aii_launcher/.../_teardown.py:341` read only `wf.workflow_id` while loading
the inputs and outputs of every non-terminal workflow. Fixed in the same
commit, so the rule arrives GREEN at 26 of 26 (25 False/False, 1 deliberate
`load_input=True`).

**A `**kwargs` dict is resolved, and an ANNOTATED one is the live shape.**
`zombie_reaper.py` builds `list_kwargs: dict = {...}` with both flags False,
then calls `list_workflows(**list_kwargs)`. Reading only the call's keywords
reports that careful site as the defect — the first version did exactly that.
Handling `ast.Assign` alone is not enough either: the live dict is an
`ast.AnnAssign`, and ten synthetic probes all passed while the real tree still
failed, because probes get written unannotated. Later `kw["k"] = v` additions
are folded in too, since that is how an optional filter joins a built dict.

Scope resolution stops at function boundaries in both directions, so an inner
function's dict cannot vouch for an outer call and no call is counted twice.

Probed fifteen ways: a bare call, a one-flag call, a dict missing a flag, and
an inner dict leaking outward all fire; both flags inline, a deliberate
`load_input=True`, plain and annotated dict literals, a subscript-added flag,
the async variant, and an unrelated method do not.

Verified the fix breaks nothing: 251 tests across the launcher-teardown,
stop-crash-recovery, run-access-gate, zombie-liveness and cost-cache groups,
0 failures. The strict keyword-only stubs the verification below warns about
have since been widened to accept both flags.

Superseded proposal, kept for its reasoning — note the filename differs from
what was built, which is itself the hazard `ready.py` trips on (a body naming
a `$RULE_DIR` path that does not exist reads as BLOCKED even when the command
works), so it is written here without that prefix:

    scripts/list_workflows_flags.py  # AST over aii_server: every
    DBOS.list_workflows call carries both load kwargs=False unless the
    enclosing function reads .input/.output or the call bears
    '# loads-io: <why>'

Delete-check: Better deletion available and the rule should enforce it: a house helper
aii_lib.dbos_app.list_workflow_meta(...) defaulting both flags False, with
direct DBOS.list_workflows banned in aii_server — single-source instead of
twelve remembered kwargs pairs. Rule text should prefer that end-state; the
kwargs check is the interim form.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Keep in the helper form its own delete-check names: house
list_workflow_meta wrapper defaulting flags off, rule bans direct
DBOS.list_workflows for metadata reads. 11/12 compliance with one silent full-
deserialization stray shows the drift is real.
- KEEP: 11/12 already comply and the miss deserializes full config snapshots
per row on a hot list path. Best form is the house helper the delete-check
names, then a grep banning direct DBOS.list_workflows — near-zero cost, recurs
at every new call site.
- KEEP: Best as its own delete-check proposes: ship list_workflow_meta helper,
then a grep bans direct DBOS.list_workflows outside it — simpler and louder
than per-call kwarg AST checking. Either form implementable.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
The library fact is CONFIRMED: `inspect.signature(DBOS.list_workflows)` on the
installed dbos prints `load_input = True` and `load_output = True`, and
reading `dbos._sys_db` source shows `if load_input:
load_columns.append(SystemSchema.workflow_status.c.inputs)` / `if load_output:
… c.output … c.error` — so the defaults add those columns to the SELECT. The
counts are wrong. My AST scan of every `*.list_workflows(...)` call in
aii_server/ found 19 call sites, not twelve: __init__.py:273/515/562,

Corrected statement of fact:
The outlier is `_owned_statuses` at
aii_server/dashboard/services/run_cost.py:351, call at :369 — not
`_workflow_statuses_for` at :366, which does not exist. The population is 19
server call sites with 18 conforming (17 explicit + zombie_reaper.py:241 via
**kwargs), not 'eleven of twelve'. The inefficiency is genuine and worth
fixing on its own. One trap for whoever fixes it: rule-server-run-access-
gate/test_staff_owner_resolution.py:159 and :174 stub `def _list_workflows(*,
workflow_ids, user)` with a strict keyword-only signature, so adding
`load_input=False, load_output=False` to the production call raises TypeError
in both tests until those stubs are widened — the change is two kwargs plus
two test-stub edits, not a one-liner.
