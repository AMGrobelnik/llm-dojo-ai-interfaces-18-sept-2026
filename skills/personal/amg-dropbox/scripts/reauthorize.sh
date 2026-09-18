#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# amg-dropbox — re-authorize the app and install the new refresh token
# =============================================================================
# Run this after CHANGING THE APP'S SCOPES in the Dropbox App Console. A scope
# change does not apply to tokens already issued, so the app can be granted
# files.content.read and the stored token still cannot download — which is
# exactly the state this repo was in on 2026-08-27, and it is invisible until
# something tries to read.
#
# Usage:  bash scripts/reauthorize.sh
#
# It prints the authorize URL (built from your own app key, so nothing has to
# be pasted in), takes the code Dropbox shows you, exchanges it, writes the new
# refresh token into this skill's .env with a timestamped backup, and then
# PROVES which scopes the new token actually carries by calling the endpoints
# rather than trusting the console.
# =============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
info() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SKILL_DIR/.env"

# Same resolution order as the uploader: env first (pods), then this .env.
_load_secret() {
    local var="$1" val=""
    if [[ -n "${!var:-}" ]]; then
        val="${!var}"
    elif [[ -f "$ENV_FILE" ]]; then
        val=$(grep -E "^${var}=" "$ENV_FILE" | tail -n1 | cut -d'=' -f2- | tr -d "\"'" || true)
    fi
    printf '%s' "$val"
}

APP_KEY="$(_load_secret DROPBOX_APP_KEY)"
APP_SECRET="$(_load_secret DROPBOX_APP_SECRET)"
if [[ -z "$APP_KEY" || -z "$APP_SECRET" ]]; then
    err "DROPBOX_APP_KEY / DROPBOX_APP_SECRET not found in the environment or $ENV_FILE"
    exit 1
fi

echo
echo "1. Open this URL while logged into the Dropbox account that owns the app,"
echo "   click Allow, and copy the code it shows:"
echo
echo -e "   ${CYAN}https://www.dropbox.com/oauth2/authorize?client_id=${APP_KEY}&token_access_type=offline&response_type=code${NC}"
echo
echo "   token_access_type=offline is what makes Dropbox return a REFRESH token"
echo "   rather than only a 4-hour access token."
echo
read -r -p "2. Paste the code here: " AUTH_CODE
[[ -n "$AUTH_CODE" ]] || {
    err "no code given"
    exit 1
}

RESP=$(curl -s --max-time 60 https://api.dropbox.com/oauth2/token \
    -d code="$AUTH_CODE" -d grant_type=authorization_code \
    -d client_id="$APP_KEY" -d client_secret="$APP_SECRET")

REFRESH=$(printf '%s' "$RESP" | python3 -c \
    "import sys,json;print(json.load(sys.stdin).get('refresh_token',''))" 2>/dev/null || true)
ACCESS=$(printf '%s' "$RESP" | python3 -c \
    "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [[ -z "$REFRESH" ]]; then
    err "no refresh_token in the response. Dropbox said:"
    printf '%s\n' "$RESP" >&2
    err "(a code is single-use and expires quickly — get a fresh one and retry)"
    exit 1
fi

# Write it in place with a dated backup. Never echoed: the point of putting it
# in .env is that it does not end up in a terminal scrollback or a transcript.
install_token() {
    local target="$1"
    if [[ -f "$target" ]]; then
        local backup
        backup="$target.bak-$(date +%Y%m%dT%H%M%SZ)"
        cp "$target" "$backup"
        chmod 600 "$backup"
        info "backed up $target -> $(basename "$backup")"
    fi
python3 - "$target" "$REFRESH" <<'PY'
import sys
from pathlib import Path

path, token = Path(sys.argv[1]), sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out, replaced = [], False
for line in lines:
    if line.startswith("DROPBOX_REFRESH_TOKEN="):
        out.append(f"DROPBOX_REFRESH_TOKEN={token}")
        replaced = True
    else:
        out.append(line)
if not replaced:
    out.append(f"DROPBOX_REFRESH_TOKEN={token}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
    chmod 600 "$target"
    info "new refresh token written to $target (not printed)"
}

# BOTH files, not just this skill's. The repo-root .env is what the deploy
# base64s into AII_ENV_B64, so a pod keeps the OLD token until that file
# moves too, and it is the file the daily db_backup daemon uploads with.
# This used to be a warning printed at the end and left to a human, which is
# a manual step in a procedure run once, months apart, under time pressure.
#
# The root file is only ever REWRITTEN, never created and never extended: it
# is touched solely when it already carries a DROPBOX_REFRESH_TOKEN line, so
# a checkout that does not use Dropbox is left completely alone. Verified in
# sync before this change — all three keys hash-identical across both files.
install_token "$ENV_FILE"

REPO_ROOT="$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
ROOT_ENV="${REPO_ROOT:+$REPO_ROOT/.env}"
if [[ -n "$ROOT_ENV" && -f "$ROOT_ENV" && "$ROOT_ENV" != "$ENV_FILE" ]] &&
    grep -qE '^DROPBOX_REFRESH_TOKEN=' "$ROOT_ENV"; then
    install_token "$ROOT_ENV"
else
    info "repo-root .env carries no DROPBOX_REFRESH_TOKEN — nothing to sync"
fi

# --- Prove what the new token can actually do -------------------------------
# The console says what it GRANTED; this says what the TOKEN carries, which is
# the thing that was wrong before. A probe path that does not exist is enough:
# `path/not_found` means the scope IS present.
#
# Dropbox refuses in TWO different shapes, and matching only the first reports
# a missing scope as present — measured 2026-08-27 against this very app:
#
#   files/*    HTTP 401  {"error":{".tag":"missing_scope",...}}
#   sharing/*  HTTP 400  plain text, "does not have the required scope '...'"
#
# So both spellings are matched. This was a real false negative in the first
# draft of this script: it reported sharing.write as present while the same
# call was being refused for lacking it.
probe() {
    local endpoint="$1" body="$2" resp
    resp=$(curl -s --max-time 30 -X POST "https://api.dropboxapi.com/2/$endpoint" \
        -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
        -d "$body" || true)
    if [[ "$resp" == *missing_scope* || "$resp" == *"required scope"* ]]; then
        echo "NO"
    else
        echo "yes"
    fi
}
NONEXISTENT='{"path":"/aii-scope-probe-does-not-exist"}'
echo
echo "Scopes the NEW token actually carries:"
printf '  files.metadata.read  %s\n' "$(probe files/get_metadata "$NONEXISTENT")"
printf '  files.content.read   %s\n' "$(probe files/get_temporary_link "$NONEXISTENT")"
printf '  sharing.write        %s\n' \
    "$(probe sharing/create_shared_link_with_settings "$NONEXISTENT")"
echo
warn "If files.content.read still says NO, the scope was not saved in the App"
warn "Console (Permissions tab -> tick -> Submit) — re-authorizing again will"
warn "not help until it is."
info "The repo-root .env was updated in the same run, so a redeploy carries"
info "the new token to pods. Anything already RUNNING holds the old one."
