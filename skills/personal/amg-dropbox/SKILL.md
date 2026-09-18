---
name: amg-dropbox
description: "Uploads, archives and backs up a file or folder to Dropbox by streaming a tar.gz in 140MB chunks, handling 20GB-plus sources on under 200MB of free disk, and mints and refreshes its own access token from a stored refresh token so no credential is ever passed in; also covers listing, downloading and sharing through the Dropbox API, and pod-side use, where the credentials arrive with the operator's .env rather than from any RunPod secret store. Use whenever a request asks to put something on Dropbox, archive or back up a run, results or output folder, offload data from a machine or pod, or move a file too large to send another way. Triggers: dropbox, upload a folder, back up results, archive a run, tar.gz to cloud, chunked upload, dropbox refresh token, offload from RunPod. NOT for: emailing or drafting a file to someone (use amg-gmail), DNS, tunnels or CDN work (use amg-cloudflare), or local file moves with no cloud destination."
---

# amg-dropbox

Tar.gz a folder and stream it to Dropbox. **Plug-and-play** — credentials and
token refresh are fully automatic; just run the script with a folder path.

## Upload a folder

```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-dropbox"
bash "$SKILL_DIR/scripts/upload_to_dropbox.sh" <folder_path> [dropbox_dest]
```

Examples:

```bash
bash "$SKILL_DIR/scripts/upload_to_dropbox.sh" runs/my_run
bash "$SKILL_DIR/scripts/upload_to_dropbox.sh" runs/my_run /research-monorepo/results
```

- `dropbox_dest` defaults to `/research-monorepo`. The uploaded file is named
  `<folder>_<timestamp>.tar.gz` (`autorename` on, so it never overwrites).
- Excludes `*.pyc`, `__pycache__`, `.venv`. Uses `pigz` + `pv` if installed.
- **Long uploads are safe**: long jobs run in the background — for a multi-GB
  upload prefer `Bash run_in_background: true` and poll the log.

## Credentials — automatic, you don't touch tokens

Dropbox access tokens expire after ~4h, so this skill stores a **permanent
refresh token** and mints fresh access tokens from it on every run (and again
mid-run if one expires). The secrets live in this skill's own `.env`:

`<skill>/.env` (gitignored) holds three keys — `DROPBOX_REFRESH_TOKEN`,
`DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET`.

The script resolves them **env-var-first, then `.env`** (same pattern as the
aii-* skills): on a RunPod pod they arrive as injected `RUNPOD_SECRET_*` env
vars; locally they come from `.env`. `.env` is gitignored (the repo-root rule +
a local `.gitignore`) so it is never committed. Dropbox app: `<dropbox-app>`.

Auto-refresh logic in `scripts/upload_to_dropbox.sh`:

- mints an access token at startup from the refresh token;
- proactively re-mints once a token is >3h old (margin under the ~4h expiry);
- reactively re-mints + retries on any `HTTP 401` during chunked upload.

## The APP and the TOKEN carry different scopes — check the token, not the console

The distinction is the whole point of this section, and it bit on
2026-08-27. `files.content.read` was ticked in the App Console that day,
and the stored refresh token still could not download: a fresh access
token minted from it returned HTTP 401 `missing_scope` with
`required_scope: files.content.read`.

**A scope grant applies at AUTHORIZATION time, not at use time.** The
refresh token is bound to whatever was granted when it was issued, and
minting a new access token from it re-issues the OLD scope set. So the
console can say the app holds a scope while every token in `.env` still
cannot use it, and nothing announces the gap until something tries to read.

Measured against app id <REDACTED>, for the token in `.env`:

| scope | app | stored token |
|---|---|---|
| `files.content.write` | yes | yes — upload works |
| `files.metadata.read` | yes | yes — get_metadata |
| `account_info.read` | yes | yes |
| `files.content.read` | **yes (2026-08-27)** | **NO until re-auth** |
| `sharing.write` | no | no |

Until the token is re-authorized, `files/download`,
`files/get_temporary_link` and `sharing/create_shared_link_with_settings`
fail with `missing_scope`, and anything that must READ BACK what it
uploaded cannot be automated — including a restore. Fix it with
`reauthorize.sh` below; do not wait for it to resolve itself, because it
will not.

**Verify an upload without downloading it.** `files/get_metadata` returns
`content_hash`, which is Dropbox's own SHA-256-per-4-MiB-block-then-SHA-256
digest. Compute the same thing on the bytes as they go out and compare — an
end-to-end integrity proof that needs no read scope.
`scripts/volume_migration_backup.py` does exactly this; its `ContentHash`
class is pinned against Dropbox's reported value for a known file in
`rules/aii/unit-tests/rule-volume-backup-verifiable/`.

**Granting a scope needs a browser** (App Console → Permissions → tick it
→ Submit), and then a re-authorization, for the reason above — the grant
binds at authorization time, so the console alone changes nothing for an
existing token:

```bash
bash "$SKILL_DIR/scripts/reauthorize.sh"
```

It builds the authorize URL from your own app key, takes the code, writes
the new refresh token into this skill's `.env` **and the repo-root `.env`**
(timestamped backup each, never echoed, both left mode 600), and then PROVES
which scopes the new token carries by calling the endpoints rather than
trusting the console.

Both files, because the repo-root one is what the deploy base64s into
`AII_ENV_B64` — a pod keeps the OLD token until that file moves too. That
used to be a warning printed at the end and left to a human. The root file
is only ever rewritten, never created and never extended: it is touched
solely when it already carries a `DROPBOX_REFRESH_TOKEN` line, so a checkout
that does not use Dropbox is left alone, mode included. A redeploy is still
what carries the new token to pods; anything already running holds the old
one.

## Doing other Dropbox API calls (list, download, share…)

Mint a fresh access token from the same `.env`, then call any Dropbox endpoint:

```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-dropbox"
set -a; . "$SKILL_DIR/.env"; set +a    # load the 3 keys (env-first still wins on pods)
ACCESS_TOKEN=$(curl -s https://api.dropbox.com/oauth2/token \
  -d grant_type=refresh_token -d refresh_token="$DROPBOX_REFRESH_TOKEN" \
  -d client_id="$DROPBOX_APP_KEY" -d client_secret="$DROPBOX_APP_SECRET" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
# e.g. list a folder:
curl -s -X POST https://api.dropboxapi.com/2/files/list_folder \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"path":"/research-monorepo"}'
```

## Using it on RunPod pods — it already works, no setup needed

**Corrected 2026-08-27; this section used to describe a setup step that is
not needed and would not be read.** It said pods take these keys from
RunPod's secret store and told you to add three account secrets injected as
`{{ RUNPOD_SECRET_* }}`. Measured on the live server pod:

| checked | result |
|---|---|
| `RUNPOD_SECRET_*` in pid 1's env | 0 |
| `DROPBOX_*` in pid 1's env | 0 |
| `DROPBOX_*` in the db_backup process | **4** |

The credentials reach a pod the same way every other secret does: the deploy
base64s the operator's repo-root `.env` into `AII_ENV_B64`
(`aii_runpod/…/deploy/env_payload.py`), `scripts/runpod/shared_init.sh`
decodes it back to `/research-monorepo/.env`, and whatever sources that file has
them. That is why the daily backup daemon has been uploading from the pod
for months with no RunPod secret configured — and why `GET /v1/secrets` is
not even a path in RunPod's v2 API.

So: nothing to set up. Put the keys in the repo-root `.env` and deploy.

## Regenerating the refresh token (only if it's ever revoked)

The refresh token never expires unless revoked or the app secret is rotated.
If you must mint a new one:

1. Open (logged into Dropbox), click **Allow**, copy the code shown:

   ```text
   https://www.dropbox.com/oauth2/authorize?client_id=<APP_KEY>&token_access_type=offline&response_type=code
   ```

   `token_access_type=offline` is what makes Dropbox return a refresh token.
2. Exchange the code (server-to-server):

   ```bash
   curl -s https://api.dropbox.com/oauth2/token \
     -d code=<AUTH_CODE> -d grant_type=authorization_code \
     -d client_id=<APP_KEY> -d client_secret=<APP_SECRET>
   ```

3. Put the returned `refresh_token` into `<skill>/.env` (and update the RunPod
   secret if pods use it). Scopes needed: `files.content.write` (set under the
   app's Permissions tab, then re-authorize if you change them).

## Notes

- **The old warning here is retired: skill `.env` files are NOT baked into
  the image.** It said the repo had no `.dockerignore` and that `COPY .`
  therefore shipped every skill `.env`. There are three
  (`.dockerignore`, `Dockerfile.server.dockerignore`,
  `Dockerfile.pipeline.dockerignore`), and the server one carries `.env` at
  line 48 and `**/.env` at line 53 with the reason written beside it —
  "secrets reach the pod at runtime via AII_ENV_B64 — no .env ever needs to
  live in the image". Confirmed on the running pod:
  `/research-monorepo/.claude/skills/amg-dropbox/` contains `scripts` and nothing
  else. The change the note asked for has already been made.
- Dropbox single-request upload cap is 150MB; this script chunks at 140MB.
