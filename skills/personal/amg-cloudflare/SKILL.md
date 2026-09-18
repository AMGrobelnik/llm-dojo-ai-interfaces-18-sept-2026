---
name: amg-cloudflare
description: "Drives the Cloudflare API for a domain ALREADY OWNED through a stdlib-only CLI, scripts/cf.py: lists zones, pulls daily traffic analytics and edge status-code totals, lists, adds, updates and deletes DNS records, reports cloudflared tunnel health, and purges CDN cache. Use whenever the request concerns Cloudflare traffic or visitor numbers for a site, a DNS record change, a CNAME or A record pointed somewhere new, proxying, tunnel health, cache flushing, an API-token setup, or anything otherwise done on dash.cloudflare.com. Triggers: Cloudflare, zone, DNS record, CNAME, A record, proxied, cache purge, tunnel, edge analytics, 4xx and 5xx totals, CLOUDFLARE_API_TOKEN. NOT for: checking whether a name is still unregistered, which is amg-is-domain-taken, or comparing registrar prices before buying, which is domain-hunter; NOT for search ranking or AI-citation visibility, which seo-geo covers; NOT for the GPU or CPU machines behind the domain, which aii-runpod provisions."
---

# amg-cloudflare

One stdlib-only CLI (`scripts/cf.py`, system `python3`, no venv) for the
Cloudflare API. Token comes from this skill's gitignored `.env` —
**never print, echo, or log the token value**.

```bash
SKILL_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo /research-monorepo)/.claude/skills/amg-cloudflare"
CF="python3 $SKILL_DIR/scripts/cf.py"
```

## Commands

```bash
$CF verify                       # check the token works
$CF zones                        # list zones (id, name, status, plan)
$CF analytics <zone>             # daily requests/uniques/cached%/threats/4xx/5xx (--days 1-31)
$CF status-codes <zone>          # edge response status totals (--days)
$CF dns <zone>                   # list DNS records (id, type, name, content, proxied)
$CF dns-add <zone> CNAME sub.example.com target.example.com --proxied
$CF dns-update <zone> <record_id> --content new.target.com
$CF dns-del <zone> <record_id>
$CF tunnels                      # list Cloudflare tunnels + connection health
$CF purge <zone> [url...]        # purge CDN cache (everything if no urls) — ASK FIRST
```

`<zone>` is a zone name (run `$CF zones` to list them) or 32-hex id.
`dns-update` keeps any field
you don't pass. `purge` with no urls flushes the whole zone cache — confirm
with the user before running it.

## One-time setup (token missing or expired)

1. Open <https://dash.cloudflare.com/profile/api-tokens> → Create Token →
   Custom token.
2. Permissions (least privilege for full skill coverage):
   - Zone → Zone → Read
   - Zone → DNS → Edit
   - Zone → Analytics → Read
   - Zone → Cache Purge → Purge
   - Account → Cloudflare Tunnel → Read
   - Account → Account Settings → Read
   Zone resources: All zones (or just the zone you manage).
3. Paste into `<SKILL_DIR>/.env` as `CLOUDFLARE_API_TOKEN=<token>`
   (file is gitignored; `.env.template` shows the format).
4. `$CF verify` must print `token OK`.

The connector credential `CLOUDFLARE_TUNNEL_TOKEN` in the repo root `.env`
is tunnel-scoped only — it cannot call the management API and is NOT what
this skill uses.
