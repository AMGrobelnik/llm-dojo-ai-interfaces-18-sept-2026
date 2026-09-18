---
name: aii-runpod
description: "Creates, lists and terminates RunPod GPU and CPU pods, plus pod templates, network volumes, SSH access, real container runtime status, GPU stock and pricing, and an orphan reaper, through ready-made scripts and call_server abilities. ALWAYS read before provisioning or tearing down cloud compute, SSHing into a pod to read logs, diagnosing a pod stuck pulling its image, or sweeping leftover pods and templates. Triggers: RunPod, pod, network volume, pod template, GPU instance, cloud GPU, rent a machine, SSH into pod, aii_runpod_gen_pod, aii_runpod_get_pod_status, EU-RO-1, cpu3g, orphaned resources, pod cost per hour. Never hand-write raw RunPod REST calls — these scripts encode the v2 API traps. NOT for measuring or budgeting hardware already on the current machine (aii-use-hardware), parallelising work across it (aii-parallel-computing), Colab notebooks (aii-colab), staged scale-up against a time budget (aii-long-running-tasks), or the DNS, tunnel and CDN layer fronting a deployed site (amg-cloudflare)."
---

## Python Scripts

Python scripts in `scripts/`. Preferred way to manage RunPod resources.

**How to run:**
```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/aii-runpod"
PY="$SKILL_DIR/../.ability_client_venv/bin/python"
$PY $SKILL_DIR/scripts/aii_runpod_get_pods.py --json
$PY $SKILL_DIR/scripts/aii_runpod_del_pod.py --pod-name my-pod
```

**IMPORTANT — Pod creation takes 300-600s** (Docker image pull). Use bash timeout ≥660s:
```bash
$PY $SKILL_DIR/scripts/aii_runpod_gen_pod.py --pod-name my-pod
```

Every script supports `--json` for raw JSON output and `--help` for flags.

**Programmatic API** (used by pipeline code and RunPodClient):

### `aii_runpod_gen_template`

Find or create a template by name.

```python
from aii_lib.abilities.ability_server import call_server
result = call_server("aii_runpod__gen_template", {
    "name": "my-template",             # required
    "image": "myimg:latest",            # default: <author>/aii_pipeline:latest
    "disk_gb": 20,                      # default: 40
    "start_cmd": "bash /start.sh",      # optional
    "ports": "8080/http",               # optional
    "env_json": '{"KEY":"val"}',        # optional
})
# Returns: success, template_id, template_name, created (bool)
```

### `aii_runpod_gen_pod`

**The 1 TB-orphan trap is FIXED — `volume_name` now defaults to `""`, meaning
attach NO volume.** It used to default to `aii_pipeline_data_eu`, which cannot
match the real hyphenated `aii-pipeline-data-eu` (`_find_by_name` is an exact
match with no normalisation), so the lookup could only ever MISS and fall
through to the create branch, minting a fresh 1 TB volume (~$70/month) on every
call that omitted a volume. A default whose only reachable outcome is an orphan
is a bill, not a default.

**To attach the production volume you must now say so**, which every production
path already did: pass `volume_id` (`runpod_backend.py` reads it from
`pod_lifecycle.orchestrator.network_volume_id`) or the correctly-spelled
`volume_name="aii-pipeline-data-eu"`. Nothing regressed in the change — the old
default could never reuse that volume, only duplicate it.

Leaving `volume_name` empty is also what you want for ephemeral pods that only
need container disk: it unpins the pod from a single datacenter and makes
allocation far more likely to succeed.

Audited 2026-08-25: two network volumes exist, `aii-pipeline-data-eu` (1000 GB,
the live one) and `other-project-vol` (10 GB, another project's). **No orphans**
— the trap never fired in production, because the private config overlay has
always supplied `network_volume_id`.

Create a CPU or GPU pod. Supports two modes:
- **Orchestrator** (default): lookup template/volume by name, wait for ready.
- **Worker**: provide `template_id`/`volume_id` directly, `skip_wait=True`.

```python
# Orchestrator pod (lookup by name, wait for ready):
result = call_server("aii_runpod__gen_pod", {
    "pod_name": "my-pod",              # default: aii_orchestrator
    "template_name": "my-template",     # lookup by name
    "volume_name": "my-vol",            # default: "" (attach no volume)
    "data_center": "EU-RO-1",           # default: EU-RO-1
    "cpu_flavor": "cpu3g",              # default: cpu3g
    "vcpu": 4,                          # default: 4
    "disk_gb": 40,                      # default: 40
})

# Worker pod (direct IDs, GPU, skip wait):
result = call_server("aii_runpod__gen_pod", {
    "pod_name": "my-worker",
    "template_id": "abc123",            # direct (skip name lookup)
    "volume_id": "vol456",              # direct (skip find/create)
    "gpu_type_id": "NVIDIA RTX A4500",  # GPU mode (omit for CPU)
    "gpu_count": 1,                     # default: 1
    "docker_start_cmd": "bash /run.sh", # override start command
    "ports": "8080/http",               # port config
    "skip_wait": True,                  # return immediately
})
# Returns: success, pod_id, pod_name, cost_per_hr,
#          volume_id, template_id
#          (+ ssh_command, ssh_host, worker_url, wait_seconds if waited)
```

### `aii_runpod_del_pod`

Terminate pod and/or delete volume by name or ID.

```python
result = call_server("aii_runpod__del_pod", {
    "pod_name": "my-pod",       # or pod_id
    "volume_name": "my-vol",    # or volume_id (optional)
})
# Returns: success, pod_terminated, volume_deleted, details
```

Supports both `pod_name`/`pod_id` and `volume_name`/`volume_id`. At least one required.

**Note:** Only named resources are affected — deleting a pod does NOT delete its volume.

### `aii_runpod_del_template`

Delete a template by name or ID.

```python
result = call_server("aii_runpod__del_template", {
    "name": "my-template",      # or template_id
})
# Returns: success, template_deleted, template_name, template_id
```

### `aii_runpod_reap_orphans`

Sweep leftovers of ALL kinds by name prefix — the on-demand janitor. Before
this, the only cleanup ran inside the ability preflight, so strays were
collected only when someone happened to run it: 8 orphaned `aii_hc_tpl_*`
templates had accumulated against 0 orphaned pods, because the pod side had a
janitor and the template side did not.

```python
result = call_server("aii_runpod__reap_orphans", {
    "prefix": "aii_hc_",        # REQUIRED — there is no "sweep everything"
    "delete": False,            # default: report only
    "kinds": "",                # default "pods,templates"; add "volumes" to opt in
    "keep": "",                 # ids or names to spare
})
# Returns: success, prefix, deleted, found: {kind: [{id, name}]}, counts, errors
```

**It reports and stops unless you pass `delete`.** A prefix is blunt: the
production templates are `aii_server` / `aii_orchestrator` / `aii_worker_*`,
so `--prefix aii_` matches all of them plus the live server pod — measured
against the real account, that dry run reports 1 pod and 5 templates, every
one load-bearing. Preview first, then narrow the prefix or use `keep`.

**Volumes are opt-in.** They are the only resource here billing by the GB and
they hold live data (`aii-pipeline-data-eu` is 1000 GB of pgdata); unmounted
does not mean unwanted.

### `aii_runpod_get_pods`

List pods with optional filters.

```python
result = call_server("aii_runpod__get_pods", {})           # all pods
result = call_server("aii_runpod__get_pods", {"prefix": "aii_worker_"})  # by prefix
result = call_server("aii_runpod__get_pods", {"pod_id": "abc123"})      # by ID
# Returns: success, pods: [{id, name, status, gpu_type, cost_per_hr, image, template_id}], count
```

### `aii_runpod_get_templates`

List templates with optional prefix filter.

```python
result = call_server("aii_runpod__get_templates", {})                    # all
result = call_server("aii_runpod__get_templates", {"prefix": "aii_worker"})  # by prefix
# Returns: success, templates: [{id, name, image, container_disk_gb, volume_gb, ports}], count
```

### `aii_runpod_get_pod_status`

Get **real** container runtime state. Unlike `get_pods`, whose `status` is RUNNING from the moment a machine is assigned, this returns `uptime_seconds` — the actual container uptime, from v2's `runtime.uptime` (null until the pod is RUNNING). Use it to detect stuck pods where the container never started despite a RUNNING status.

```python
result = call_server("aii_runpod__get_pod_status", {"pod_id": "abc123"})
# Returns: success, pod_id, name, desired_status,
#          uptime_seconds (0 = not started),
#          container_running (bool),
#          host_id, gpu_display, ports, cost_per_hr
```

**Key fields:**
- `container_running: false` + `uptime_seconds: 0` → image pulling or stuck
- `container_running: true` + `uptime_seconds: N` → container running for N seconds
- `host_id: ""` → no machine assigned yet

**`container_running: false` DOES NOT PROVE THE CONTAINER IS DEAD.** This
field was added because v1's `desiredStatus` lied in one direction — it read
`RUNNING` from the moment of creation, so it could never say a pod was still
coming up. `container_running` lies in the OTHER direction, and still does:
v2's `status` fixed the first problem (it reports the state the pod is
actually in) but this field is derived from `runtime.uptime`, which is a
separate signal and is unaffected by that rename.
Observed 2026-08-14 on orchestrator pod `z9ahjjticqfmzm`: three
consecutive samples reported `container_running=False, uptime_seconds=0`
while the process inside was demonstrably alive — still appending to
`sinks/otel/metrics.jsonl` on the shared volume every ~5 minutes. A dead
container cannot write files.

The trap is that it is *usually* right, so a control test makes it look
trustworthy: the server pod in the same account, same CPU flavor, reported
`container_running=True, uptime=109655` correctly at that moment. One
correct sample is not evidence the field is reliable for a different pod,
and concluding "dead" from it led to a wrong diagnosis and nearly to a
reap of a live run.

**Before acting on a "dead container" reading, corroborate with something
the pod itself produces:**
- File mtimes under the run dir on the shared network volume — read them
  from ANOTHER pod that mounts it (the server pod), so no dependency on the
  suspect pod being reachable. Sample twice: a growing file is proof of
  life that no API can contradict.
- The run's journal (`sinks/events/events.jsonl`) vs its OTEL sinks. Both
  frozen ⇒ genuinely stopped. Metrics advancing while events are frozen ⇒
  the process lives and the WORK is wedged, which is a completely
  different fault with a completely different fix.

### `aii_runpod_get_instance_availability`

**NEVER TRUST THIS TO DECIDE WHETHER YOU CAN GET A POD. JUST TRY CREATING ONE.**

It reports `Available: NO` for GPU types that create perfectly well, and it has
reported `stock: High` for types that then fail to allocate. The only reliable
availability test is `aii_runpod_gen_pod` itself: attempt the creation, and read
the result. Use this script for PRICING, and for nothing else.

When a creation attempt does fail, read the error before blaming stock:

- `could not find any pods with required specifications` usually means YOUR SPEC
  is unsatisfiable, not that the GPU is gone. The most common cause is a network
  volume: a volume pins the pod to that volume's datacenter (e.g. EU-RO-1), so
  you are asking for one GPU type in one region. Pass an empty `volume_name` to
  attach no volume at all (container disk only) and let RunPod place the pod
  anywhere — then retry the same GPU type.
- The scripts EXIT 0 even when the API returns HTTP 500, so the exit code tells
  you nothing. Detect success by finding a pod id / ssh command in the output.
- **ALWAYS `get_pods` after a create loop, and terminate strays.** A loop that
  tries several GPU types and misjudges its own success detection will create a
  pod on every "failed" iteration. That happened here: four pods were left
  RUNNING ($0.49 + $0.49 + $0.56 + $0.74/hr) while the loop reported that every
  attempt had failed. Listing the pods is the only trustworthy check that you
  created exactly what you meant to.
- `del_pod`'s CLI now takes `--pod-id` / `--volume-id` as well as the name
  flags, and the id wins. It used to expose names ONLY, which mattered more
  than it sounds: delete-by-name resolves through a listing, and a name that
  does not match prints `No pod found` and exits 0 — indistinguishable from a
  successful delete. Four stray workers were "terminated" that way on
  2026-08-22 and were still RUNNING afterwards. **Prefer the id**, and confirm
  with `get_pods` rather than trusting the exit code. It terminates ONE pod per
  call, so if several pods share a name, call it repeatedly until it reports
  `No pod found`.

Check GPU stock availability via the v2 catalog. Returns stock status, max available
GPUs, and pricing. GPU-only — CPU instances don't have an availability query.

Used by `WorkerPod._start_pod_with_fallback()` to skip out-of-stock GPUs before wasting retries.

```python
result = call_server("aii_runpod__get_instance_availability", {
    "gpu_type_id": "NVIDIA RTX A4500",  # required
    "gpu_count": 1,                      # default: 1
    "secure_cloud": True,                # default: True
})
# Returns: success, gpu_type_id, display_name, memory_gb,
#          stock_status ("LOW"/"MEDIUM"/"HIGH"/null under v2),
#          available (bool),
#          max_gpu_count       — the tier's static ceiling, ignores stock
#          available_gpu_counts — 1..max when available, [] when not
#          secure_price, spot_price
```

**Key fields:**
- `available: false` + `stock_status: null` → GPU out of stock, skip to fallback
- `stock_status: "Low"` → few GPUs left, may fail during creation
- `stock_status: "High"` → plenty available

### `aii_runpod_get_volumes`

List network volumes with optional name filter.

```python
result = call_server("aii_runpod__get_volumes", {})                          # all
result = call_server("aii_runpod__get_volumes", {"name": "aii-pipeline-data-eu"})  # exact name
# Returns: success, volumes: [{id, name, size, data_center_id}], count
```

---

## Bash Scripts

### Create Template (gen_template.sh)

Finds or creates a template by name. Env vars passed as JSON.

```bash
bash scripts/gen_template.sh --name my-template --env-json '{"KEY":"value"}'
```

Flags: `--name` (required), `--image`, `--disk-gb`, `--start-cmd`, `--ports`, `--env-json`

### Create Pod (gen_runpod.sh)

Looks up template by name (must exist), finds/creates volume, creates CPU pod, waits for running.

```bash
bash scripts/gen_runpod.sh
bash scripts/gen_runpod.sh --vcpu 8 --pod-name my-pod --template-name my-template
```

Flags:

| Flag | Default | Values |
|------|---------|--------|
| `--pod-name` | `aii_orchestrator` | any |
| `--template-name` | `aii_orchestrator` | must exist |
| `--volume-name` | `""` (none) | find/create |
| `--volume-size-gb` | `1000` | GB |
| `--data-center` | `EU-RO-1` | EU/US DCs |
| `--cpu-flavor` | `cpu3g` | cpu3c/g/m, cpu5c/g/m |
| `--vcpu` | `4` | integer |
| `--disk-gb` | `40` | container disk |
| `--image` | `<author>/aii_pipeline:latest` | Docker |

CPU flavors: `c`=compute, `g`=general, `m`=memory. Number is generation (3 or 5).

### Teardown (stop_runpod.sh)

```bash
bash scripts/stop_runpod.sh --pod-name my-pod --volume-name my-vol
bash scripts/stop_runpod.sh --pod-name my-pod
```

Flags: `--pod-name`, `--volume-name` (at least one required)

---

## REST API (for anything scripts don't cover)

```bash
source "$PROJECT_ROOT/.env"

_rp() {
    local method="$1" path="$2" body="${3:-}"
    local args=(-s -X "$method" "https://api.runpod.io/v2${path}"
        -H "Content-Type: application/json"
        -H "Authorization: Bearer $RUNPOD_API_KEY"
        --max-time 30)
    [[ -n "$body" ]] && args+=(-d "$body")
    curl "${args[@]}"
}
```

**List:** `_rp GET /pods`, `_rp GET /network-volumes`, `_rp GET /templates`
— v2 WRAPS these (`{"pods": […]}`, `{"templates": […]}`,
`{"networkVolumes": […]}`) where v1 returned a bare list. Iterating the
response directly yields dict KEYS, not records.

**Stop/Start:** one action route, not two —
`_rp POST /pods/$PID/action '{"action":"stop"}'`. Valid actions are
`start`, `stop`, `restart`, `terminate`; anything else is a 422 that
enumerates them. v1's dedicated `/pods/$PID/stop` and `/start` are gone.

**Terminate:** `_rp DELETE /pods/$PID`

**SSH:** take it from the pod itself — `.ssh.direct.command` (a routable
`root@ip -p port`) or `.ssh.proxy.command` (`<id>-<hash>@ssh.runpod.io`).
v2 hands back the finished command, so there is no host id to reassemble.

---

## SSH into Pods

`get_pod_status` prints the full SSH command (public IP + mapped port). Pipeline logs: `/research-monorepo/aii_pipeline/runs/`

---

### API Bugs & Gotchas

1. **Env vars on pods** with `networkVolumeId` + >=9 inline env vars. Always use templates.
2. **`volumeMountPath` no longer exists.** v2 templates take only a `persistent` mount (rejected on CPU pods), and a NETWORK volume carries its own path at pod-create time: `mounts.network[].path`, which has **no default and must be set explicitly**.
3. **`publicIp` is not a pod field in v2.** A pod's reachable address comes from `ssh.direct` (host/port) or the TCP entries in `runtime.ports`. HTTP ports are proxy-served and report a CGNAT ip (`100.65.x`) that cannot be dialed — filter on `type == "tcp"`. Use `get_pod_status` for the resolved public IP + SSH command.
4. **Concurrent `POST /pods` returns 500.** Creating 3+ pods simultaneously causes "Something went wrong" errors. Stagger creation by ~5s per pod.
5. **`status=RUNNING` ≠ container running.** v2 reports RUNNING immediately after machine assignment, but the Docker image pull takes ~300s. Use `aii_runpod_get_pod_status` (v2 `runtime.uptime`) for real state.

---

## AII Pipeline Defaults

| Resource | Name |
|----------|------|
| Volume | `aii-pipeline-data-eu` (hyphens; see note below) |
| Orchestrator template | `aii_orchestrator` |
| Worker templates | `aii_worker_{gpu,cpu_heavy,cpu_light}` |
| Data center | `EU-RO-1` |
| Docker image | pinned per deploy to a commit SHA |

The volume name really is hyphenated — the underscore spelling
`aii_data_eu` matches nothing, and `_find_by_name` is exact.

**The templates carry NO env and NO RunPod secrets.** This section used to
say "9 secrets" and list them as `{{ RUNPOD_SECRET_<NAME> }}`. Measured
2026-08-27 against `GET /v1/templates`: `aii_orchestrator`, `aii_server` and
`aii_worker_cpu_light` each report **0 env keys and 0 `RUNPOD_SECRET`
references**. Nothing in `aii_runpod/` or `aii_server/` sets that field
either, and `GET /v1/secrets` is not a path in the v2 API.

Secrets reach pods a different way, which is why nothing broke: the deploy
base64s the operator's repo-root `.env` into `AII_ENV_B64`
(`aii_runpod/…/deploy/env_payload.py` — the full file for the ability-server
pod, a 22-key allowlist for the rest), and `scripts/runpod/shared_init.sh`
decodes it on the pod. Do not create RunPod account secrets; nothing reads
them. (The old list also included `DROPBOX_TOKEN`, which has no reader at
all and was removed from the allowlist on the same day.)

**If the script fails** with a connection error (ability server not running): create a local `.venv`, install server deps from `server_requirements.txt` into it, then import the `@aii_ability` function from the script and call it directly — bypassing the server:
```bash
uv venv .venv --python=3.12 && uv pip install --python=.venv/bin/python -r "$SKILL_DIR/scripts/server_requirements.txt"
```
