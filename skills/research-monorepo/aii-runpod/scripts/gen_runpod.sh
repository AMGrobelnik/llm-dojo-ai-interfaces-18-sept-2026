#!/usr/bin/env bash
# Create RunPod CPU pod with existing template + volume (find/create volume only)
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC}   $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

# Defaults
DATA_CENTER="EU-RO-1"
# Empty = attach no volume. The old default could not match the real
# hyphenated aii-pipeline-data-eu, so it only ever created 1 TB orphans.
VOLUME_NAME=""
VOLUME_SIZE_GB=1000
POD_NAME="aii_orchestrator"
TEMPLATE_NAME="aii_orchestrator"
CPU_FLAVOR="cpu3g"
VCPU_COUNT=4
CONTAINER_DISK_GB=40
# v2 requires an explicit mount path for a network volume — its
# NetworkMount has "no default, must be specified explicitly", where v1
# inferred one. Matches execution.runpod.volume_mount_path.
VOLUME_MOUNT_PATH="/research-monorepo/aii_data"
DOCKER_IMAGE="<author>/aii_pipeline:latest"

need_arg() { [[ $# -ge 2 ]] || fail "$1 requires a value"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --data-center)    need_arg "$@"; DATA_CENTER="$2"; shift 2 ;;
        --volume-name)    need_arg "$@"; VOLUME_NAME="$2"; shift 2 ;;
        --volume-size-gb) need_arg "$@"; VOLUME_SIZE_GB="$2"; shift 2 ;;
        --pod-name)       need_arg "$@"; POD_NAME="$2"; shift 2 ;;
        --template-name)  need_arg "$@"; TEMPLATE_NAME="$2"; shift 2 ;;
        --cpu-flavor)     need_arg "$@"; CPU_FLAVOR="$2"; shift 2 ;;
        --vcpu)           need_arg "$@"; VCPU_COUNT="$2"; shift 2 ;;
        --disk-gb)        need_arg "$@"; CONTAINER_DISK_GB="$2"; shift 2 ;;
        --image)          need_arg "$@"; DOCKER_IMAGE="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "  --pod-name NAME       Pod name (default: aii_orchestrator)"
            echo "  --template-name NAME  Template name — must exist (default: aii_orchestrator)"
            echo "  --volume-name NAME    Volume name (default: none — attach no volume)"
            echo "  --volume-size-gb GB   Volume size if creating (default: 1000)"
            echo "  --data-center ID      Data center (default: EU-RO-1)"
            echo "                        EU: EU-RO-1 EU-SE-1 EU-CZ-1 EU-NL-1 EU-FR-1"
            echo "                        US: US-TX-3 US-IL-1 US-GA-1 US-CA-2 US-KS-2 ..."
            echo "  --cpu-flavor ID       CPU flavor (default: cpu3g)"
            echo "                        Gen3: cpu3c (compute) cpu3g (general) cpu3m (memory)"
            echo "                        Gen5: cpu5c (compute) cpu5g (general) cpu5m (memory)"
            echo "  --vcpu N              vCPU count (default: 4)"
            echo "  --disk-gb GB          Container disk in GB (default: 40)"
            echo "  --image IMAGE         Docker image (default: <author>/aii_pipeline:latest)"
            exit 0
            ;;
        *) fail "Unknown option: $1" ;;
    esac
done

# Load API key
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

if [[ -z "${RUNPOD_API_KEY:-}" && -f "$PROJECT_ROOT/.env" ]]; then
    RUNPOD_API_KEY=$(grep -E '^RUNPOD_API_KEY=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
    export RUNPOD_API_KEY
fi
[[ -z "${RUNPOD_API_KEY:-}" ]] && fail "RUNPOD_API_KEY not set"

_rp() {
    local method="$1" path="$2" body="${3:-}"
    local args=(-s -w '\n%{http_code}' -X "$method" "https://api.runpod.io/v2${path}"
        -H "Content-Type: application/json"
        -H "Authorization: Bearer $RUNPOD_API_KEY"
        --max-time 30)
    [[ -n "$body" ]] && args+=(-d "$body")
    local raw; raw=$(curl "${args[@]}")
    local code="${raw##*$'\n'}"
    local response="${raw%$'\n'*}"
    if [[ "$code" =~ ^[45] ]]; then
        echo -e "  ${RED}[FAIL]${NC} API error (HTTP $code $method $path): $response" >&2
        exit 1
    fi
    echo "$response"
}

_find() {
    local json="$1" name="$2"
    # v2 wraps collections ({"pods": [...]}, {"templates": [...]},
    # {"networkVolumes": [...]}) where v1 answered a bare list. Iterating the
    # dict yields KEYS, so x.get() raises on a str — and the 2>/dev/null||true
    # below turns that into "not found", which reads as success while the pod
    # is left running. Unwrap whichever list the payload carries.
    echo "$json" | FIND_NAME="$name" python3 -c "
import json, os, sys
d = json.loads(sys.stdin.read())
items = d if isinstance(d, list) else next(
    (v for v in d.values() if isinstance(v, list)), []
)
for x in items:
    if isinstance(x, dict) and x.get('name') == os.environ['FIND_NAME']:
        print(x['id']); break
" 2>/dev/null || true
}

# --- Template (must exist) ---
ALL_TEMPLATES=$(_rp GET /templates)
TEMPLATE_ID=$(_find "$ALL_TEMPLATES" "$TEMPLATE_NAME")
[[ -z "$TEMPLATE_ID" ]] && fail "Template '$TEMPLATE_NAME' not found. Create it first with gen_template.sh"
ok "Template: $TEMPLATE_NAME ($TEMPLATE_ID)"

# --- Volume (find or create) ---
ALL_VOLUMES=$(_rp GET /network-volumes)
VOLUME_ID=$(_find "$ALL_VOLUMES" "$VOLUME_NAME")
if [[ -n "$VOLUME_ID" ]]; then
    ok "Volume: $VOLUME_NAME ($VOLUME_ID)"
else
    info "Creating volume: $VOLUME_NAME (${VOLUME_SIZE_GB}GB)..."
    # ``dataCenter``, NOT the pod's ``dataCenterId`` — a v2 NetworkVolume and
    # a v2 Pod genuinely spell it differently, and v2 rejects unknown fields,
    # so the old spelling made this a guaranteed 422.
    RESULT=$(_rp POST /network-volumes "{\"name\":\"$VOLUME_NAME\",\"size\":$VOLUME_SIZE_GB,\"dataCenter\":\"$DATA_CENTER\"}")
    VOLUME_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])" 2>/dev/null || true)
    [[ -z "$VOLUME_ID" ]] && fail "Failed: $RESULT"
    ok "Created volume: $VOLUME_NAME ($VOLUME_ID)"
fi

# --- Pod (no inline env, no volumeMountPath) ---
info "Creating pod: $POD_NAME (${CPU_FLAVOR} x${VCPU_COUNT}vCPU)..."
RESULT=$(_rp POST /pods "{
    \"name\":\"$POD_NAME\",
    \"image\":\"$DOCKER_IMAGE\",
    \"cpu\":{\"id\":\"$CPU_FLAVOR\",\"vcpuCount\":$VCPU_COUNT},
    \"disk\":$CONTAINER_DISK_GB,
    \"mounts\":{\"network\":[{\"volumeId\":\"$VOLUME_ID\",\"path\":\"$VOLUME_MOUNT_PATH\"}]},
    \"templateId\":\"$TEMPLATE_ID\",
    \"cloud\":\"SECURE\",
    \"dataCenterIds\":[\"$DATA_CENTER\"]
}")
POD_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])" 2>/dev/null || true)
[[ -z "$POD_ID" ]] && fail "Failed: $RESULT"
COST=$(echo "$RESULT" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('cost','?'))" 2>/dev/null || echo "?")
ok "Created pod: $POD_NAME ($POD_ID, \$${COST}/hr)"

# --- Wait for container ready (runtime.uptime > 0) ---
# Was a GraphQL poll: REST v1 carried no runtime section, so uptime and the
# host id had to come from there. v2 has both — ``runtime.uptime`` (null until
# the pod is RUNNING) and a ready-made proxy SSH command, so the host id no
# longer has to be dug out and re-assembled.
info "Waiting for pod..."
SSH_CMD=""
for i in $(seq 1 120); do
    POD_JSON=$(_rp GET "/pods/$POD_ID")
    STATUS=$(echo "$POD_JSON" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('status',''))" 2>/dev/null || true)
    UPTIME=$(echo "$POD_JSON" | python3 -c "import sys,json; r=json.loads(sys.stdin.read()).get('runtime') or {}; print(r.get('uptime',0) or 0)" 2>/dev/null || echo "0")
    SSH_CMD=$(echo "$POD_JSON" | python3 -c "import sys,json; p=(json.loads(sys.stdin.read()).get('ssh') or {}).get('proxy') or {}; print(p.get('command','') or '')" 2>/dev/null || true)

    if [[ "$STATUS" == "EXITED" || "$STATUS" == "ERROR" || "$STATUS" == "TERMINATED" ]]; then
        echo ""
        fail "Pod entered terminal state: $STATUS"
    fi
    if [[ "$UPTIME" -gt 0 && -n "$SSH_CMD" ]]; then
        echo ""
        ok "Pod ready: $POD_NAME ($POD_ID, \$${COST}/hr)"
        echo ""
        echo -e "  ${CYAN}${SSH_CMD}${NC}"
        echo ""
        exit 0
    fi
    printf "\r  [INFO] %-12s (%ds)" "$STATUS" "$((i * 5))"
    sleep 5
done
echo ""
fail "Timeout waiting for pod (pod_id=$POD_ID)"
