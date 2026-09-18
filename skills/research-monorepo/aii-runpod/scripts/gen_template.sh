#!/usr/bin/env bash
# Create or find a RunPod template by name
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC}   $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }

# Defaults
TEMPLATE_NAME=""
DOCKER_IMAGE="<author>/aii_pipeline:latest"
CONTAINER_DISK_GB=40
DOCKER_START_CMD=""
PORTS=""
ENV_JSON="{}"

need_arg() { [[ $# -ge 2 ]] || fail "$1 requires a value"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name)       need_arg "$@"; TEMPLATE_NAME="$2"; shift 2 ;;
        --image)      need_arg "$@"; DOCKER_IMAGE="$2"; shift 2 ;;
        --disk-gb)    need_arg "$@"; CONTAINER_DISK_GB="$2"; shift 2 ;;
        --start-cmd)  need_arg "$@"; DOCKER_START_CMD="$2"; shift 2 ;;
        --ports)      need_arg "$@"; PORTS="$2"; shift 2 ;;
        --env-json)   need_arg "$@"; ENV_JSON="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --name NAME [OPTIONS]"
            echo ""
            echo "  --name NAME        Template name (required)"
            echo "  --image IMAGE      Docker image (default: <author>/aii_pipeline:latest)"
            echo "  --disk-gb GB       Container disk (default: 40)"
            echo "  --start-cmd CMD    Docker start command"
            echo "  --ports PORTS      Port config (e.g. '8080/http')"
            echo "  --env-json JSON    Env vars as JSON object (e.g. '{\"KEY\":\"val\"}')"
            exit 0
            ;;
        *) fail "Unknown option: $1" ;;
    esac
done

[[ -z "$TEMPLATE_NAME" ]] && fail "--name is required"

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

# Check existing
ALL_TEMPLATES=$(_rp GET /templates)
EXISTING_ID=$(_find "$ALL_TEMPLATES" "$TEMPLATE_NAME")

if [[ -n "$EXISTING_ID" ]]; then
    ok "Template already exists: $TEMPLATE_NAME ($EXISTING_ID)"
    exit 0
fi

# Build request body
BODY=$(T_NAME="$TEMPLATE_NAME" T_IMAGE="$DOCKER_IMAGE" T_DISK="$CONTAINER_DISK_GB" \
       T_CMD="$DOCKER_START_CMD" T_PORTS="$PORTS" T_ENV="$ENV_JSON" \
       python3 -c "
import json, os, sys
body = {
    'name': os.environ['T_NAME'],
    'image': os.environ['T_IMAGE'],
    'disk': int(os.environ['T_DISK']),
}
try:
    env = json.loads(os.environ['T_ENV'])
except json.JSONDecodeError as e:
    print(f'Invalid --env-json: {e}', file=sys.stderr); sys.exit(1)
if env:
    body['env'] = env
if os.environ['T_CMD']:
    # v2 takes a JSON-encoded string here, not an array.
    body['args'] = json.dumps({'cmd': ['bash', '-c', os.environ['T_CMD']]})
if os.environ['T_PORTS']:
    body['ports'] = [p.strip() for p in os.environ['T_PORTS'].split(',')]
print(json.dumps(body))
") || fail "Failed to build request body (check --env-json)"

info "Creating template: $TEMPLATE_NAME..."
RESULT=$(_rp POST /templates "$BODY")
TEMPLATE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])" 2>/dev/null || true)
[[ -z "$TEMPLATE_ID" ]] && fail "Failed: $RESULT"

# Verify template exists
info "Verifying template was created..."
ALL_TEMPLATES=$(_rp GET /templates)
VERIFY_ID=$(_find "$ALL_TEMPLATES" "$TEMPLATE_NAME")
[[ -z "$VERIFY_ID" ]] && fail "Template created but not found on verification"
ok "Template ready: $TEMPLATE_NAME ($TEMPLATE_ID)"
