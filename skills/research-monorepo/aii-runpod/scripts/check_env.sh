#!/bin/bash
# Check RunPod prerequisites: RUNPOD_API_KEY
set -euo pipefail

ERRORS=0
PROJECT_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"

RUNPOD_API_KEY="${RUNPOD_API_KEY:-}"
if [ -z "$RUNPOD_API_KEY" ] && [ -f "$PROJECT_ROOT/.env" ]; then
    RUNPOD_API_KEY=$(grep -E '^RUNPOD_API_KEY=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || true)
fi

if [ -z "$RUNPOD_API_KEY" ]; then
    echo "RUNPOD_API_KEY not set" >&2
    ERRORS=$((ERRORS + 1))
fi

exit $ERRORS
