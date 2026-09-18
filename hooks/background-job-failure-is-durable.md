<!-- hook: background-job-failure-is-durable -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every background job that clears an in-flight start mark records a durable, user-visible terminal failure on its exception path — a client never learns a job died only by outliving a watchdog

Both drivers now record. The population is what actually strands a user: a
function that CLEARS AN IN-FLIGHT START MARK and catches broad `Exception`
must record a durable terminal failure there. In
`aii_server/dashboard/services/run_jobs.py` both qualifying drivers comply:
`_run_start_runpod_job` pairs `logger.exception(...)` with `await
_record_start_failure_safe(run_id=..., username=..., detail=str(e))` under
a comment naming the symptom ("the sidebar projection alone can't surface
the failure … instead of the FE showing a phantom in-progress run forever"),
and `_run_fork_stage_job` does the same (run_jobs.py:316-324) since
`e39b8dd35071` closed the divergence this rule found. The recorded row is
what `runs_sidebar.list_runs_for_user` overlays as a synthetic 'failed to
start' entry, so a dead job surfaces its real reason within one ~2 s
sidebar poll instead of after the frontend's 600 s fork watchdog
(aii_frontend/features/runs-list/_use-dashboard/_launch.ts:50-58).

## History — the divergence as found (2026-08-24, fixed by e39b8dd35071)

`_run_fork_stage_job`'s handler did only `logger.exception(f"fork stage job
{job_id} failed for {fork_run_id}: {e}")`; `git grep -n
'record_start_failure' -- aii_server/dashboard/services/run_jobs.py`
returned hits only on the start path, and run_fork.py's
`stage_and_spawn_fork` failure branches logged + `_rollback_staged_fork()`
and never recorded — its docstring called error handling "self-contained"
because "nobody is waiting on a response to carry the error", true of the
HTTP response but not of the user. The cost was measured in the frontend: a
fork got `timeoutMs: 600_000` and then "Fork didn't start — The fork was
accepted but its run never journaled within 10 minutes … Check the server
log for stage_and_spawn_fork" — 10 blind minutes ending in log-diving
instructions a dashboard user cannot follow, where the fresh-start path
surfaced the real reason within one ~2 s sidebar poll. Distinct from
rule-server-start-admission (prompt persisted + active-count before
provisioning) and rule-server-sidebar-status (status mapping is a pure
function of workflow rows) — neither says a dead job must leave a row.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: degradation-contracts)

Command (BUILT — `scripts/check_job_failure_recorded.py`), no condition:

    python3 $RULE_DIR/scripts/check_job_failure_recorded.py

**The census missed a third driver, and it must NOT be gated the same way.**
`run_resume._provision_resume` is also fire-and-forget, also catches broad
`Exception`, and also only logs — but its run already has a DBOS workflow row,
and `runs_sidebar._overlay_start_failures` deliberately skips ids that do
("the journal is then the authority"). A start-failure row written for a
resume is a write nobody displays, so requiring one would be a gate insisting
on a useless side effect. A resume that crashes genuinely lacks a durable
signal; that needs a mechanism which does not exist yet, and is not this one.

So the population is derived from what actually strands a user: a function
that CLEARS AN IN-FLIGHT START MARK and catches broad `Exception` must record
a terminal failure there. That admits both `run_jobs` drivers and correctly
excludes the resume path.

Verified to bite with a byte-identical restore: removing the fork job's record
fails naming the function and line; the live tree passes with 2 drivers
checked.

Proposed condition: `git diff --cached --name-only -- aii_server/dashboard | grep -q .`

Delete-check: Cannot delete by making /fork synchronous again — run_fork.py:24-28 records
that inline staging outlived the FE proxy's upstream timeout, returned a bare
500, and had the handler cancelled mid-mirror leaking cloned buckets. The
deletable half is the CLIENT side: with a durable failure row for every job,
the 600 s launchWatchdog stops being the primary signal and demotes to a
backstop, and its bespoke per-launch copy collapses. That is the end state the
rule enforces — one durable record, one poll, one message.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
$ awk 'NR>=203 && NR<=214' aii_server/dashboard/services/run_jobs.py except
Exception as e: # Terminal: this fire-and-forget job has no retry ... Record
it so # ``runs_sidebar.list_runs_for_user`` overlays a synthetic # "failed to
start" row instead of the FE showing a phantom # in-progress run forever.
logger.exception(f"start_runpod job {job_id} failed: {e}") await
_record_start_failure_safe(run_id=run_id, username=aii_user, detail=str(e)) $
sed -n '314,320p' aii_server/dashboard/services/run_jobs.py except Exception
as e: logger.exception(f"fork stage job {job_id} failed for {fork_run_id}:
{e}") finally: _clear_inflight_start(aii_user, fork_run_id) await
_unregister_task(fork_run_id, job_id) $ git grep -n '_record_start_failure' --
aii_server aii_server/dashboard/services/run_jobs.py:213 (the only call site)
aii_server/dashboard/services/run_jobs.py:219 (the def) $ sed -n '300,400p'
aii_server/dashboard/api/run_fork.py | grep -n
'except|_rollback_staged_fork|logger' -> 5 failure branches, all logger.* +
await _rollback_staged_fork(); zero durable records $ sed -n '280,292p'
aii_server/dashboard/api/run_fork.py (stage_and_spawn_fork docstring) "...so
error handling is self-contained: every failure (and a /stop cancel) logs and
rolls back the staged state ... (nobody is waiting on a response to carry the
error...)" $ sed -n '50,58p' aii_frontend/features/runs-list/_use-
dashboard/_launch.ts if (launch.kind === "fork") { timeoutMs: 600_000, title:
"Fork didn't start", description: "...never journaled within 10 minutes ...
Check the server log for stage_and_spawn_fork and aii_data/logs/runs/." }
Coverage check: $ find .claude/skills/amg-hooks/rules -path '*rule-
server-start-admission*' -name '*.py' | xargs grep -ln fork -> only
test_active_runs_quota_inflight.py / test_run_start_user_isolation.py /
test_inflight_registry_concurrency.py (quota + isolation, never failure
recording). rule-server-fork-lineage ships only test_run_fork_dispatch.py /
test_run_lineage.py / test_run_config_fork_snapshot.py — no failure-durability
assertion.

Corrected statement of fact:
Every factual claim re-measured and confirmed, including the two docstrings
and the FE copy. One caveat worth carrying into the rule: rule-server-start-
admission [ENFORCED] already names BOTH
aii_server/dashboard/services/run_jobs.py and run_start_failures.py in its
condition pathspec, and its own statement ends '...a provisioning or
terminally-failed run appears in the runs list instead of vanishing'. So this
is adjacent in spirit and would fire on the same staged files; it is NOT a
duplicate (its six tests never touch run_fork.py or the fork job, verified
above), but the new rule should either scope its condition to run_fork.py +
run_jobs.py's fork half or be folded in as a new test module under start-
admission rather than a fresh group.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Population is real (run_jobs.py:172,266, run_resume.py:503,
side_chat_dispatch.py:234 fire-and-forget create_task). A job that dies with
no durable terminal record leaves the user watching a spinner until a client
watchdog fires; not covered by rule-server-start-admission or rule-pipeline-
stop-crash-recovery.
- KEEP: Population is enumerable by AST (fire-and-forget spawn sites) and the
assertion is structural — the except path calls the durable recorder. Loud
with a spawn-site count floor. Distinct from rule-no-silent-except, which a
log-only handler satisfies while the user still learns nothing.
- KEEP: No collapse available — the delete-check's alternative (make /fork
synchronous again) is recorded in run_fork.py:24-28 as having already outlived
the FE proxy's upstream timeout. Distinct from ENFORCED rule-no-silent-except
(a logged failure still leaves the client waiting on a watchdog) and from
rule-server-fork-lineage / rule-pipeline-stop-crash-recovery, which are …
