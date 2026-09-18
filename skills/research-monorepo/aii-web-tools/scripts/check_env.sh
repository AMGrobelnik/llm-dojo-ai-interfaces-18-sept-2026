#!/bin/bash
# Check web tools prerequisites.
#
# Web search is free-first: the keyless general engines (ddgs, marginalia) and
# scholarly APIs (OpenAlex, Crossref) need NO key. SERPER_API_KEY is only the
# paid last-resort fallback, so a missing key is a non-fatal note, not an error —
# search still works on the free engines.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"

SERPER_API_KEY="${SERPER_API_KEY:-}"
if [ -z "$SERPER_API_KEY" ] && [ -f "$PROJECT_ROOT/.env" ]; then
    SERPER_API_KEY=$(grep -E '^SERPER_API_KEY=' "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || true)
fi

if [ -z "$SERPER_API_KEY" ]; then
    echo "SERPER_API_KEY not set — free engines still work; no paid Serper fallback." >&2
fi

exit 0
