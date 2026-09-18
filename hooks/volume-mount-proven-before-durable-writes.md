<!-- hook: volume-mount-proven-before-durable-writes -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A pod boot proves the shared network volume is mounted before writing any durable state under it; an absent mount fails the boot closed instead of being `mkdir -p`'d onto container-local disk

Nothing anywhere tests for a mount. Ran `git grep -nE
'ismount|mountpoint|findmnt|/proc/mounts' -- '*.py' '*.sh'` → no hits at all
(outside the rule engine). Meanwhile run_server.sh:98 is `mkdir -p "$(dirname
"$PG_LOG")" "$PG_DATA" "$PROJECT_ROOT/logs"` with
`PG_DATA="${PROJECT_ROOT}/aii_data/db/pgdata"` (line 85) — unconditional. The
one place that acknowledges the failure mode is shared_init.sh:161-162, `if [[
! -d "$PROJECT_ROOT/aii_data" ]]; then warn "NFS volume $PROJECT_ROOT/aii_data
not mounted — projects/ stays pod-local (cross-pod fork/resume will fail)"` —
which (a) only warns, and (b) is a directory-existence test, so it passes on
every boot after the first one silently created the tree locally. That the
repo ships this warning is the evidence the unmounted case is considered
reachable; the response chosen is prose, not a stop. The chain past it is all
green-on-empty: pg_boot_guard.sh's own header says "Absent file (fresh, never-
booted volume) or own identity recorded → claim immediately, no wait", so the
single-writer lease passes; initdb then makes a NEW empty cluster;
`_wait_postgres_ready` (aii_runpod/deploy/_remote/_redeploy.py:43-50) is a TCP
connect and passes; `/agent_abilities/health`
(aii_server/agent_abilities/api.py:46-65) returns 200 on `_ready` alone. So a
redeploy completes GREEN onto an empty database while the real pgdata sits
untouched on the detached volume. No claimed rule covers this: rule-dbos-
bootstrap is concurrency, rule-server-db-backup is backups, rule-pod-logs-
survive-teardown is log placement, rule-runpod-redeploy-safety checks
preconditions of the SWAP, not of the store underneath it.

Re-checked 2026-08-28: run_server.sh:85 `PG_DATA=`, :98 unconditional
`mkdir -p`, shared_init.sh:162 warn-only; `git grep -nE
'ismount|mountpoint|findmnt|/proc/mounts' -- '*.py' '*.sh'` is still empty
outside the rule engine. Nothing in the chain has moved.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: degradation-contracts)

Proposed command (implemented at approval):

    bash "$RULE_DIR/scripts/check_volume_mount_gate.sh"  # (a) shared_init.sh defines require_shared_volume() using mountpoint -q/findmnt and exits nonzero; (b) every mkdir -p / redirect in scripts/runpod/*.sh whose target is under $PROJECT_ROOT/aii_data is lexically preceded in that script by a require_shared_volume call; (c) self-proving: run the helper against a temp dir that is not a mountpoint and require rc!=0, so the gate cannot ship vacuous. Local dev opts out via one named env flag set only off-pod.

Proposed condition: `git diff --cached --name-only -- scripts/runpod aii_runpod/src/aii_runpod/deploy | grep -q .`

Delete-check: Cannot delete the volume — cross-pod fork/resume and the DBOS journal require
shared durable state (session_store.py:23 pins the SAME absolute path on every
pod for exactly this). Cannot delete the check by making the mount a
container-level guarantee: RunPod attaches it via the pod spec and the boot
script cannot assert that from outside, which is precisely why shared_init.sh
already carries the weaker probe. Enforce the deleted end state instead: ONE
require_shared_volume helper, called once per boot script before the first
durable write, so no site re-decides and the existing -d test collapses into
it.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
$ git grep -nE 'ismount|mountpoint|findmnt|/proc/mounts' -- '*.py' '*.sh' (no
output at all -- zero hits tree-wide, including the rule engine) Every link in
the chain verified by reading the source: - scripts/runpod/run_server.sh:84
`PG_DATA="${PROJECT_ROOT}/aii_data/db/pgdata"` and :98 `mkdir -p "$(dirname
"$PG_LOG")" "$PG_DATA" "$PROJECT_ROOT/logs"` -- unconditional, no guard
between them. (The proposal cited :85 for PG_DATA; it is :84. Trivial.) -
scripts/runpod/shared_init.sh:161-162, verbatim: `if [[ ! -d
"$PROJECT_ROOT/aii_data" ]]; then` / `warn "NFS volume $PROJECT_ROOT/aii_data
not mounted -- projects/ stays pod-local (cross-pod fork/resume will fail)"`.
Confirmed warn-only (no exit/return), and confirmed a directory-EXISTENCE
test, so it self-heals into a false pass once anything mkdir -p's the tree
locally. - scripts/runpod/pg_boot_guard.sh:29-30 header, verbatim: "Absent
file (fresh, never-booted volume) or own identity recorded (same-container re-
run) -> claim immediately, no wait." So the single-writer lease passes on an
empty local tree. - _redeploy.py:43-51 `_wait_postgres_ready` docstring
confirms it is a TCP-connect gate: "(A full ``SELECT 1`` would need the DB
password; a successful connect is a sufficient readiness proxy.)" -
aii_server/agent_abilities/api.py:48-65 `/health`: `status = "ok" if _ready
else "starting"` / `code = 200 if _ready else 503` -- 200 on the in-process
flag alone, no store check. So a redeploy confirms GREEN over a fresh empty
cluster. Holds. ONE NUANCE the proposal's "nothing anywhere" overstates
slightly, though it does not touch the pgdata path:
aii_lib/src/aii_lib/run/agent_worker_server.py:812-825 DOES fail closed on the
volume contract for the WORKER role -- `elif is_runpod(): raise
RuntimeError("worker server: no internal key resolvable on a RunPod pod ...
The shared-volume .internal_key is missing or unreadable; check the network-
volume mount.")`. That is an artifact-existence test, not a mount primitive
(hence invisible to the proposal's grep), and it guards control-endpoint auth
on a different pod role -- the server pod's durable pgdata write remains
entirely unguarded. Worth citing in the rule as the in-repo precedent for the
fail-closed shape rather than as a counterexample. DEDUPE: clean. Grepped
claimed_r3.txt for mount|volume|nfs|pgdata|postgres|boot -- rule-pod-logs-
survive-teardown (log PLACEMENT on the volume), rule-uv-cache-mount-discipline
(Dockerfile uv cache mounts), rule-dbos-bootstrap (CREATE TABLE races), rule-
runpod-redeploy-safety (swap preconditions), rule-pod-boot-handoff-parity
(literal parity across the Python/bash seam). None proves the store underneath
is mounted.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Confirmed zero ismount/mountpoint/findmnt hits tree-wide, so nothing
proves the shared volume before durable writes; a missed mount silently mkdir
-p's run state onto ephemeral container disk. Boot-time one-shot, near-zero
per-commit cost, not covered by rule-pod-logs-survive-teardown (log placement
only).
- KEEP: Confirmed zero mountpoint/ismount/findmnt hits tree-wide, so the check
is a presence assertion on one boot script plus a unit test — deterministic
and loud (the script's existence is the population floor). Not covered by
rule-pod-logs-survive-teardown, which presumes the mount rather than proving
it.
- KEEP: The one candidate in this batch where the delete-check genuinely
fails: cross-pod fork/resume and the DBOS journal require shared durable
state, so the volume cannot go. Zero coverage today — `git grep -nE
'ismount|mountpoint|findmnt|/proc/mounts' -- '*.py' '*.sh'` returns nothing
tree-wide. Not claimed: rule-no-runtime-state-in-tree pins where paths POINT,
not whether …

OWNER-GATED: the mechanism asserts a boot-time hard stop that does not exist yet; adding it changes whether a pod boots at all. Worth the decision — an absent mount currently yields a GREEN redeploy onto an empty database — but it is a decision, not a script.

## Mechanism (built 2026-09-03)

**The helper.** `scripts/runpod/volume_gate.sh` defines exactly one function,
`require_shared_volume`, and does nothing else when sourced. It resolves
`${PROJECT_ROOT:-<its own ../..>}/aii_data` — the path IS the mount point
(`execution.runpod.volume_mount_path`, applied to every template by
`pod_templates.template_specs_from_config`) — tests it with `mountpoint -q`,
falls back to `findmnt -n --target … -o TARGET` equalling that same path, and
on failure prints a loud block naming the path and the failure chain it
prevents, then `exit 1`. Fail-closed: it stops the boot rather than warning.

It is a separate file rather than a block inside `shared_init.sh` because two
entrypoints write under the volume BEFORE they source shared_init: run_server.sh
creates and opens its volume boot-log mirror at the top of the file, and
run_pipeline.sh opens the per-run `aii_data/runs/<id>/logs/orchestrator.log`
sink before its own source line. Hoisting those `source shared_init.sh` lines
instead would push shared_init's own boot output out of the two logs those
blocks exist to produce. One definition, four callers.

**Call sites.**

| script | gate sits before | guards |
|---|---|---|
| `shared_init.sh` | (after `PROJECT_ROOT`) | every sourcing role |
| `run_server.sh` | the volume log mirror | pgdata, 2 secrets |
| `run_pipeline.sh` | the run-log sink | `runs/<id>/logs` |
| `race_barrier.sh` | `mkdir -p "$RACE_DIR"` | volume rendezvous |

`shared_init.sh` is the role-independent one: server, orchestrator, worker and
`worker_pod.py`'s `bash -c 'source … && python'` all reach it. The warn-only
`-d` probe at its old :161-162 is gone, collapsed into this call exactly as the
Delete-check proposed. `run_worker.sh` needs no call of its own — it writes
nothing under the volume and sources shared_init. `pg_boot_guard.sh` takes its
heartbeat path as `$1`, so the checker cannot attribute that write to the
volume; its one caller gates above it.

`race_barrier.sh` runs as its own process (`bash race_barrier.sh`), so it
cannot inherit a shell function; in production its call is the second one, and
it costs one `mountpoint` syscall.

**Off-pod opt-out.** One named flag, `AII_SHARED_VOLUME_OPTIONAL=1`, returns 0
with a one-line notice. Local dev needs no change and none was made: nothing in
`aii_launcher` or `scripts/local` sources these scripts except
`runpod_docker_emulate.sh`, which mounts a named docker volume at
`/research-monorepo/aii_data` for both containers — a real mount point inside the
container, so it passes the gate unaided. The flag is for a deliberately
volume-less pod (`aii_runpod_gen_pod` with no volume id, which defaults to the
`aii_orchestrator` template) or a bare checkout; pass it in the pod's `env`.

**What the checker asserts** (`scripts/check_volume_mount_gate.sh`, `--root`
optional): (a) `require_shared_volume` is defined exactly once under
scripts/runpod, its body uses `mountpoint` and `findmnt`, exits nonzero and
carries the opt-out, and `shared_init.sh` both has it and calls it; (b) in every
`scripts/runpod/*.sh`, each line that writes under `aii_data` is lexically
preceded by that call or by sourcing shared_init.sh — printed as `path:line:`.
The scan RESOLVES variables transitively (`PG_DATA` from `aii_data`, `WON` from
`RACE_DIR`) because the write this rule exists for names `$PG_DATA` and never
`aii_data`, so a literal scan reports that exact line clean; (c) a self-proof
that sources the helper against a temp `PROJECT_ROOT` (rc must be nonzero) and
again with the opt-out set (rc must be 0). Exit 2 if shared_init.sh is missing —
discovery never fails open.

**Measured 2026-09-03.** On the real tree: **exit 0**. Population floor, with
every gate marker stripped from a copy: **28 durable-write sites** across
run_server.sh, run_pipeline.sh, race_barrier.sh and shared_init.sh, including
`mkdir -p "$(dirname "$PG_LOG")" "$PG_DATA" …`, `.dbos_password` and
`.django_secret_key`. Mutants: removing run_server.sh's own call → exit 1 with
its three pre-source writes named; a helper gutted to `return 0` while still
carrying the words `mountpoint`, `findmnt` and the flag → exit 1 from clause
(c), which is the clause that stops the gate shipping vacuous; a tree without
shared_init.sh → exit 2. The rule's
pytest module: **3 passed in 0.32s**. shellcheck (`--severity=warning -x
-o check-unassigned-uppercase`) and shfmt clean on all six boot scripts and on
the checker; ruff check + format clean on the test.

**Consequence to accept before approving.** A pod whose volume is genuinely
absent now refuses to boot, and RunPod will restart-loop it with the failure
block in the container log. That is the point — the alternative is the GREEN
redeploy over an empty database this rule was written about — but it is a
behaviour change for any deployment configured with an empty
`network_volume_id`, and for ad-hoc volume-less pods booted from a role
template. Both take `AII_SHARED_VOLUME_OPTIONAL=1`.
