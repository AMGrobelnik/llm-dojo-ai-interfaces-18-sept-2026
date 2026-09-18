#!/usr/bin/env bash
# Stop RunPod pod and/or delete network volume by name.
# Provide --pod-name to terminate a pod, --volume-name to delete a volume, or both.
# At least one must be provided.
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC}   $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }

POD_NAME=""
POD_ID=""
VOLUME_NAME=""

need_arg() { [[ $# -ge 2 ]] || fail "$1 requires a value"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pod-name)    need_arg "$@"; POD_NAME="$2"; shift 2 ;;
        --pod-id)      need_arg "$@"; POD_ID="$2"; shift 2 ;;
        --volume-name) need_arg "$@"; VOLUME_NAME="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "  --pod-name NAME     Terminate pod with this name"
            echo "  --pod-id ID         Terminate pod with this ID (skips name lookup)"
            echo "  --volume-name NAME  Delete volume with this name"
            echo ""
            echo "Provide --pod-name, --pod-id, and/or --volume-name. At least one is required."
            exit 0
            ;;
        *) fail "Unknown option: $1" ;;
    esac
done

[[ -z "$POD_NAME" && -z "$POD_ID" && -z "$VOLUME_NAME" ]] && fail "Provide --pod-name, --pod-id, and/or --volume-name"

# Load API key
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

if [[ -z "${RUNPOD_API_KEY:-}" && -f "$PROJECT_ROOT/.env" ]]; then
    RUNPOD_API_KEY=$(grep -E '^RUNPOD_API_KEY=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
    export RUNPOD_API_KEY
fi
[[ -z "${RUNPOD_API_KEY:-}" ]] && fail "RUNPOD_API_KEY not set"

# REST helper
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

# --- Terminate pod ---
if [[ -n "$POD_ID" || -n "$POD_NAME" ]]; then
    # Resolve pod ID: use --pod-id directly, or look up by --pod-name
    if [[ -z "$POD_ID" ]]; then
        ALL_PODS=$(_rp GET /pods)
        POD_ID=$(_find "$ALL_PODS" "$POD_NAME")
        if [[ -z "$POD_ID" ]]; then
            warn "No pod found: $POD_NAME"
        fi
    fi
    if [[ -n "$POD_ID" ]]; then
        _POD_LABEL="${POD_NAME:+$POD_NAME ($POD_ID)}"
        _POD_LABEL="${_POD_LABEL:-$POD_ID}"
        info "Terminating: $_POD_LABEL..."
        _rp DELETE "/pods/$POD_ID" > /dev/null
        # Verify pod is gone
        info "Verifying pod terminated..."
        CHECK="$POD_ID"
        for _ in $(seq 1 12); do
            ALL_PODS=$(_rp GET /pods)
            CHECK=$(echo "$ALL_PODS" | POD_ID="$POD_ID" python3 -c "
import json, os, sys
for x in json.loads(sys.stdin.read()):
    if x.get('id') == os.environ['POD_ID']: print(x['id']); break
" 2>/dev/null || true)
            [[ -z "$CHECK" ]] && break
            sleep 5
        done
        if [[ -n "$CHECK" ]]; then
            fail "Pod still exists after termination: $_POD_LABEL"
        fi
        ok "Pod terminated: $_POD_LABEL"
    fi
fi

# --- Delete volume ---
if [[ -n "$VOLUME_NAME" ]]; then
    ALL_VOLUMES=$(_rp GET /network-volumes)
    VOLUME_ID=$(_find "$ALL_VOLUMES" "$VOLUME_NAME")
    if [[ -z "$VOLUME_ID" ]]; then
        warn "No volume found: $VOLUME_NAME"
    else
        info "Deleting volume: $VOLUME_NAME ($VOLUME_ID)..."
        # Retry — RunPod may still be detaching pods from the volume
        DELETED=false
        for attempt in $(seq 1 12); do
            DEL_RAW=$(curl -s -w '\n%{http_code}' -X DELETE \
                "https://api.runpod.io/v2/network-volumes/$VOLUME_ID" \
                -H "Content-Type: application/json" \
                -H "Authorization: Bearer $RUNPOD_API_KEY" \
                --max-time 30)
            DEL_CODE="${DEL_RAW##*$'\n'}"
            if [[ ! "$DEL_CODE" =~ ^[45] ]]; then
                DELETED=true
                break
            fi
            printf "\r  [INFO] Waiting for pods to detach... (%ds)" "$((attempt * 5))"
            sleep 5
        done
        if [[ "$DELETED" != "true" ]]; then
            echo ""
            fail "Failed to delete volume after retries: $VOLUME_NAME"
        fi
        echo ""
        # Verify volume is gone
        info "Verifying volume deleted..."
        for _ in $(seq 1 12); do
            ALL_VOLUMES=$(_rp GET /network-volumes)
            CHECK=$(_find "$ALL_VOLUMES" "$VOLUME_NAME")
            [[ -z "$CHECK" ]] && break
            sleep 5
        done
        if [[ -n "$CHECK" ]]; then
            fail "Volume still exists after deletion: $VOLUME_NAME"
        fi
        ok "Volume deleted: $VOLUME_NAME ($VOLUME_ID)"
    fi
fi

echo ""
ok "Done"
