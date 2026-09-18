#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# amg-dropbox — Tar.gz & Upload a folder to Dropbox (streaming, plug-and-play)
# =============================================================================
# Usage:
#   bash scripts/upload_to_dropbox.sh <folder_path> [dropbox_dest]
#
# Examples:
#   bash scripts/upload_to_dropbox.sh runs/my_run
#   bash scripts/upload_to_dropbox.sh runs/my_run /research-monorepo/results
#
# CREDENTIALS — fully automatic, you never pass a token:
#   Needs DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET.
#   Resolved env-var-first (RunPod injects them as RUNPOD_SECRET_* on pods),
#   else from this skill's own .env (../.env, gitignored) for local use.
#   The script mints a short-lived (~4h) access token from the refresh token
#   and AUTO-REFRESHES it (proactively past 3h, and reactively on any 401),
#   so long uploads never die on token expiry.
#
# Uses pigz (parallel gzip) if available, else gzip; pv for progress if present.
# Streaming design: tar | pigz | split -> upload each chunk as it appears, so
# only ONE 140MB chunk is on disk at a time. Handles 20GB+ with <200MB disk.
# =============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

human_size() {
    local bytes=$1
    if ((bytes >= 1073741824)); then
        printf "%.1fGB" "$(echo "$bytes / 1073741824" | bc -l)"
    elif ((bytes >= 1048576)); then
        printf "%dMB" $((bytes / 1048576))
    elif ((bytes >= 1024)); then
        printf "%dKB" $((bytes / 1024))
    else
        printf "%dB" "$bytes"
    fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)" # skill root holds .env

MAX_RETRIES=3
CURL_CONNECT_TIMEOUT=30
CURL_MAX_TIME=600 # 10 min per chunk

# --- Resolve secrets: env-var-first, fall back to this skill's .env ----------
# (Same convention as the aii-* skills: pods inject secrets as env vars; locally
#  they live in the skill's gitignored .env. Never returns non-zero, so the
#  validation below can print a friendly error instead of set -e aborting.)
_load_secret() {
    local var="$1" val=""
    if [[ -n "${!var:-}" ]]; then
        val="${!var}"
    elif [[ -f "$SKILL_DIR/.env" ]]; then
        val=$(grep -E "^${var}=" "$SKILL_DIR/.env" | tail -n1 | cut -d'=' -f2- | tr -d "\"'" || true)
    fi
    printf '%s' "$val"
}

DROPBOX_REFRESH_TOKEN="$(_load_secret DROPBOX_REFRESH_TOKEN)"
DROPBOX_APP_KEY="$(_load_secret DROPBOX_APP_KEY)"
DROPBOX_APP_SECRET="$(_load_secret DROPBOX_APP_SECRET)"

if [[ -z "$DROPBOX_REFRESH_TOKEN" || -z "$DROPBOX_APP_KEY" || -z "$DROPBOX_APP_SECRET" ]]; then
    err "Missing Dropbox credentials. Need DROPBOX_REFRESH_TOKEN, DROPBOX_APP_KEY,"
    err "DROPBOX_APP_SECRET — set them in the environment or in $SKILL_DIR/.env"
    exit 1
fi

# --- Optional encryption (AES-256 via gpg symmetric) -------------------------
# If DROPBOX_GPG_PASSPHRASE is set (env-first, else .env) the archive stream is
# encrypted before chunking:  tar | pigz | gpg --symmetric | split.  The upload
# gets a .gpg suffix. Decrypt later with:  gpg -d FILE.tar.gz.gpg | tar -xz
GPG_PASSPHRASE="$(_load_secret DROPBOX_GPG_PASSPHRASE)"
ENCRYPT=0
ARCHIVE_EXT="tar.gz"
GPG_PPF=""
if [[ -n "$GPG_PASSPHRASE" ]]; then
    if ! command -v gpg &>/dev/null; then
        err "DROPBOX_GPG_PASSPHRASE is set but gpg is not installed."
        exit 1
    fi
    ENCRYPT=1
    ARCHIVE_EXT="tar.gz.gpg"
    GPG_PPF="$(mktemp)"
    chmod 600 "$GPG_PPF"
    printf '%s' "$GPG_PASSPHRASE" >"$GPG_PPF"
    trap 'rm -f "${GPG_PPF:-}"' EXIT # superseded by the large-path trap below
    info "Encryption: ${CYAN}ON${NC} (AES-256, gpg symmetric)"
fi

# Pipeline filters: encryption (a no-op `cat` when disabled) and a tar that
# tolerates "file changed as we read it" (exit 1) — expected when archiving a
# live working tree; only a real fatal error (exit >1) aborts the run.
enc_filter() {
    if [[ "$ENCRYPT" == "1" ]]; then
        gpg --batch --yes --pinentry-mode loopback --passphrase-file "$GPG_PPF" \
            --symmetric --cipher-algo AES256 -o -
    else
        cat
    fi
}
tar_safe() {
    # ``|| ec=$?``, never a bare call. Under the ``set -e`` at the top, a bare
    # ``tar`` that exits 1 — "file changed as we read it", the ordinary case on
    # a live working tree, and the whole reason this wrapper exists — kills the
    # shell before ``ec`` is ever read. The tolerance below then never runs and
    # the pipeline fails via pipefail, aborting the upload for the exact
    # condition it was written to ignore.
    local ec=0
    tar "$@" || ec=$?
    ((ec > 1)) && return "$ec"
    return 0
}

# --- Access-token minting + auto-refresh -------------------------------------
DROPBOX_TOKEN=""
TOKEN_MINTED_AT=0

mint_access_token() {
    local json
    json=$(curl -s --max-time "$CURL_CONNECT_TIMEOUT" \
        https://api.dropbox.com/oauth2/token \
        -d grant_type=refresh_token \
        -d refresh_token="$DROPBOX_REFRESH_TOKEN" \
        -d client_id="$DROPBOX_APP_KEY" \
        -d client_secret="$DROPBOX_APP_SECRET" || true)
    DROPBOX_TOKEN=$(printf '%s' "$json" |
        python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
    if [[ -z "$DROPBOX_TOKEN" ]]; then
        err "Failed to mint a Dropbox access token from the refresh token."
        err "Dropbox response: ${json:-<empty>}"
        err "(Refresh token revoked/rotated? Re-run the authorize flow — see SKILL.md.)"
        exit 1
    fi
    TOKEN_MINTED_AT=$(date +%s)
}

# Proactively refresh before Dropbox's ~4h expiry (margin = 3h).
ensure_fresh_token() {
    local age=$(($(date +%s) - TOKEN_MINTED_AT))
    if ((age >= 10800)); then
        info "Access token ${age}s old — refreshing"
        mint_access_token
    fi
}

mint_access_token
info "Authenticated to Dropbox (minted fresh access token, valid ~4h)"

# --- Args --------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    err "Usage: $0 <folder_path> [dropbox_dest]"
    exit 1
fi

FOLDER_PATH="$1"
DROPBOX_DEST="${2:-/research-monorepo}"

if [[ ! -d "$FOLDER_PATH" ]]; then
    err "Folder not found: $FOLDER_PATH"
    exit 1
fi

FOLDER_NAME="$(basename "$FOLDER_PATH")"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_NAME="${FOLDER_NAME}_${TIMESTAMP}.${ARCHIVE_EXT}"
DROPBOX_FILE_PATH="${DROPBOX_DEST}/${ARCHIVE_NAME}"

# --- Pick compressor (pigz = parallel, gzip = fallback) ----------------------
if command -v pigz &>/dev/null; then
    COMPRESSOR="pigz"
    CORES=$(nproc 2>/dev/null || echo 4)
    info "Using ${CYAN}pigz${NC} (${CORES} cores)"
else
    COMPRESSOR="gzip"
    warn "pigz not found — falling back to single-threaded gzip"
fi

# --- Count files -------------------------------------------------------------
FILE_COUNT=$(find "$FOLDER_PATH" -type f ! -name '*.pyc' ! -path '*/__pycache__/*' ! -path '*/.venv/*' | wc -l)
FOLDER_SIZE=$(du -sb "$FOLDER_PATH" | cut -f1)
info "Found ${CYAN}${FILE_COUNT}${NC} files ($(human_size "$FOLDER_SIZE") uncompressed)"

# --- Retry helper ------------------------------------------------------------
curl_with_retry() {
    local description="$1"
    shift
    local attempt
    for ((attempt = 1; attempt <= MAX_RETRIES; attempt++)); do
        if "$@"; then
            return 0
        fi
        if ((attempt < MAX_RETRIES)); then
            local backoff=$((attempt * 5))
            warn "${description} failed (attempt ${attempt}/${MAX_RETRIES}), retrying in ${backoff}s..."
            sleep "$backoff"
        else
            err "${description} failed after ${MAX_RETRIES} attempts"
            return 1
        fi
    done
}

# --- Upload a single chunk, set CHUNK_HTTP_CODE ------------------------------
upload_chunk() {
    local method="$1" # start, append, finish
    local chunk_file="$2"
    local session_id="${3:-}"
    local offset="${4:-0}"

    local url header
    case "$method" in
        start)
            url="https://content.dropboxapi.com/2/files/upload_session/start"
            header="{\"close\": false}"
            ;;
        append)
            url="https://content.dropboxapi.com/2/files/upload_session/append_v2"
            header="{\"cursor\": {\"session_id\": \"${session_id}\", \"offset\": ${offset}}, \"close\": false}"
            ;;
        finish)
            url="https://content.dropboxapi.com/2/files/upload_session/finish"
            header="{\"cursor\": {\"session_id\": \"${session_id}\", \"offset\": ${offset}}, \"commit\": {\"path\": \"${DROPBOX_FILE_PATH}\", \"mode\": \"add\", \"autorename\": true}}"
            ;;
    esac

    # --progress-bar -> stderr (visible on terminal), -w http_code -> stdout (captured)
    CHUNK_HTTP_CODE=$(curl --progress-bar \
        --connect-timeout "$CURL_CONNECT_TIMEOUT" \
        --max-time "$CURL_MAX_TIME" \
        -o /tmp/dropbox_chunk_response.json \
        -w "%{http_code}" \
        -X POST "$url" \
        -H "Authorization: Bearer $DROPBOX_TOKEN" \
        -H "Dropbox-API-Arg: $header" \
        -H "Content-Type: application/octet-stream" \
        --data-binary @"$chunk_file")

    # Token expired mid-upload? Re-mint and signal a retry (with the fresh token).
    if [[ "$CHUNK_HTTP_CODE" == "401" ]]; then
        warn "Access token expired (HTTP 401) — re-minting"
        mint_access_token
        return 1
    fi

    [[ "$CHUNK_HTTP_CODE" == "200" ]]
}

# --- Small file: single upload -----------------------------------------------
if [[ "$FOLDER_SIZE" -le $((140 * 1024 * 1024)) ]]; then
    ARCHIVE_PATH="/tmp/$ARCHIVE_NAME"
    info "Small folder — compressing to single archive"
    tar_safe --exclude='*.pyc' --exclude='__pycache__' --exclude='.venv' \
        --warning=no-file-changed --ignore-failed-read \
        -cf - -C "$(dirname "$FOLDER_PATH")" "$FOLDER_NAME" |
        $COMPRESSOR | enc_filter >"$ARCHIVE_PATH"

    ARCHIVE_SIZE=$(stat --format="%s" "$ARCHIVE_PATH" 2>/dev/null || stat -f "%z" "$ARCHIVE_PATH")
    info "Archive: $(human_size "$ARCHIVE_SIZE")"

    # Token was just minted (valid ~4h) — a small single-shot upload can't outlast it.
    info "Uploading to Dropbox: ${CYAN}${DROPBOX_FILE_PATH}${NC}"
    HTTP_CODE=$(curl --progress-bar \
        --connect-timeout "$CURL_CONNECT_TIMEOUT" \
        --max-time "$CURL_MAX_TIME" \
        -o /tmp/dropbox_response.json -w "%{http_code}" \
        -X POST https://content.dropboxapi.com/2/files/upload \
        -H "Authorization: Bearer $DROPBOX_TOKEN" \
        -H "Dropbox-API-Arg: {\"path\": \"$DROPBOX_FILE_PATH\", \"mode\": \"add\", \"autorename\": true}" \
        -H "Content-Type: application/octet-stream" \
        --data-binary @"$ARCHIVE_PATH")

    if [[ "$HTTP_CODE" == "200" ]]; then
        info "Upload complete: ${CYAN}${DROPBOX_FILE_PATH}${NC}"
        rm -f "$ARCHIVE_PATH"
    else
        err "Upload failed (HTTP $HTTP_CODE)"
        cat /tmp/dropbox_response.json 2>/dev/null
        rm -f "$ARCHIVE_PATH"
        exit 1
    fi
    exit 0
fi

# ==========================================================================
# Large file: streaming compress -> split -> upload one chunk at a time
# ==========================================================================
CHUNK_SIZE=$((140 * 1024 * 1024)) # 140MB chunks (under 150MB API limit)
CHUNK_DIR=$(mktemp -d)
STATE_FILE="/tmp/dropbox_upload_state_${TIMESTAMP}.json"
trap 'rm -rf "$CHUNK_DIR" /tmp/dropbox_chunk_response.json; rm -f "${GPG_PPF:-}"; echo -e "\n${YELLOW}[WARN]${NC} State saved: $STATE_FILE (for debugging)"' EXIT

info "Streaming compress + split into ${CYAN}$(human_size "$CHUNK_SIZE")${NC} chunks"
info "Destination: ${CYAN}${DROPBOX_FILE_PATH}${NC}"

# Stream: tar | pv (progress) | pigz | split — only one chunk on disk at a time
if command -v pv &>/dev/null; then
    tar_safe --exclude='*.pyc' --exclude='__pycache__' --exclude='.venv' \
        --warning=no-file-changed --ignore-failed-read \
        -cf - -C "$(dirname "$FOLDER_PATH")" "$FOLDER_NAME" |
        pv -s "$FOLDER_SIZE" -N "Compressing" |
        $COMPRESSOR |
        enc_filter |
        split -b "$CHUNK_SIZE" -a 4 -d --additional-suffix=.part - "$CHUNK_DIR/chunk_"
else
    info "Install ${CYAN}pv${NC} for compression progress (apt install pv)"
    tar_safe --exclude='*.pyc' --exclude='__pycache__' --exclude='.venv' \
        --warning=no-file-changed --ignore-failed-read \
        -cf - -C "$(dirname "$FOLDER_PATH")" "$FOLDER_NAME" |
        $COMPRESSOR |
        enc_filter |
        split -b "$CHUNK_SIZE" -a 4 -d --additional-suffix=.part - "$CHUNK_DIR/chunk_"
fi

# Collect chunk files in order (find, not ls — robust to odd names; empty if none)
mapfile -t CHUNK_FILES < <(find "$CHUNK_DIR" -maxdepth 1 -name 'chunk_*.part' | sort)
TOTAL_CHUNKS=${#CHUNK_FILES[@]}

if [[ $TOTAL_CHUNKS -eq 0 ]]; then
    err "No chunks produced — compression may have failed"
    exit 1
fi

TOTAL_BYTES=0
for cf in "${CHUNK_FILES[@]}"; do
    TOTAL_BYTES=$((TOTAL_BYTES + $(stat --format="%s" "$cf")))
done

info "Compressed to $(human_size "$TOTAL_BYTES") in ${CYAN}${TOTAL_CHUNKS}${NC} chunks"

# --- Upload session: start with first chunk ----------------------------------
OFFSET=0
CHUNK_NUM=1
FIRST_CHUNK="${CHUNK_FILES[0]}"
FIRST_SIZE=$(stat --format="%s" "$FIRST_CHUNK")

info "[${CHUNK_NUM}/${TOTAL_CHUNKS}] Starting session + uploading $(human_size "$FIRST_SIZE")"

ensure_fresh_token
curl_with_retry "Session start" upload_chunk "start" "$FIRST_CHUNK"
SESSION_ID=$(python3 -c "import json; print(json.load(open('/tmp/dropbox_chunk_response.json'))['session_id'])")
OFFSET=$FIRST_SIZE
rm -f "$FIRST_CHUNK"
info "  $(human_size "$OFFSET") / $(human_size "$TOTAL_BYTES") uploaded"

# Save state for debugging
python3 -c "
import json
json.dump({
    'session_id': '$SESSION_ID',
    'dropbox_path': '$DROPBOX_FILE_PATH',
    'total_chunks': $TOTAL_CHUNKS,
    'total_bytes': $TOTAL_BYTES
}, open('$STATE_FILE', 'w'), indent=2)
"

# --- Upload middle chunks ----------------------------------------------------
for ((i = 1; i < TOTAL_CHUNKS - 1; i++)); do
    CHUNK_NUM=$((i + 1))
    CHUNK_FILE="${CHUNK_FILES[$i]}"
    CHUNK_BYTES=$(stat --format="%s" "$CHUNK_FILE")
    PROGRESS=$((OFFSET * 100 / TOTAL_BYTES))

    info "[${CHUNK_NUM}/${TOTAL_CHUNKS}] Uploading $(human_size "$CHUNK_BYTES") (${PROGRESS}%)"

    ensure_fresh_token
    curl_with_retry "Chunk ${CHUNK_NUM}" upload_chunk "append" "$CHUNK_FILE" "$SESSION_ID" "$OFFSET"

    if [[ "$CHUNK_HTTP_CODE" != "200" ]]; then
        err "Chunk ${CHUNK_NUM} failed with HTTP ${CHUNK_HTTP_CODE}"
        cat /tmp/dropbox_chunk_response.json 2>/dev/null
        exit 1
    fi

    OFFSET=$((OFFSET + CHUNK_BYTES))
    rm -f "$CHUNK_FILE"
    info "  $(human_size "$OFFSET") / $(human_size "$TOTAL_BYTES") uploaded"
done

# --- Upload final chunk + commit --------------------------------------------
CHUNK_NUM=$TOTAL_CHUNKS
LAST_FILE="${CHUNK_FILES[-1]}"
LAST_SIZE=$(stat --format="%s" "$LAST_FILE")
PROGRESS=$((OFFSET * 100 / TOTAL_BYTES))

info "[${CHUNK_NUM}/${TOTAL_CHUNKS}] Finishing — uploading $(human_size "$LAST_SIZE") (${PROGRESS}%)"

ensure_fresh_token
curl_with_retry "Final chunk" upload_chunk "finish" "$LAST_FILE" "$SESSION_ID" "$OFFSET"

if [[ "$CHUNK_HTTP_CODE" != "200" ]]; then
    err "Final chunk failed with HTTP ${CHUNK_HTTP_CODE}"
    cat /tmp/dropbox_chunk_response.json 2>/dev/null
    exit 1
fi

rm -f "$LAST_FILE"

# --- Result ------------------------------------------------------------------
info "Upload complete: ${CYAN}${DROPBOX_FILE_PATH}${NC} ($(human_size "$TOTAL_BYTES"))"
rm -f "$STATE_FILE"

# Clean trap
trap - EXIT
rm -rf "$CHUNK_DIR" /tmp/dropbox_chunk_response.json
rm -f "${GPG_PPF:-}"
