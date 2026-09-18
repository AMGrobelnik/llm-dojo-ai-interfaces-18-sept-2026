#!/usr/bin/env python3
"""Cloudflare management CLI — zones, DNS, analytics, tunnels, cache.

Stdlib-only (no deps). Reads CLOUDFLARE_API_TOKEN from the skill-local
.env (gitignored) or the environment. The token value is never printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
SKILL_DIR = Path(__file__).resolve().parent.parent


def _load_token() -> str:
    env_file = SKILL_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("CLOUDFLARE_API_TOKEN=") and line.split("=", 1)[1]:
                return line.split("=", 1)[1].strip().strip('"')
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if tok:
        return tok
    sys.exit(
        "ERROR: no CLOUDFLARE_API_TOKEN. Create one at "
        "https://dash.cloudflare.com/profile/api-tokens (see SKILL.md for "
        f"the permission list) and paste it into {env_file} as "
        "CLOUDFLARE_API_TOKEN=<token>"
    )


def _req(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_load_token()}",
            "Content-Type": "application/json",
        },
    )
    try:
        # B310 audits the scheme: every url here is built on the https API constants above.
        with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310
            out = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            out = json.load(e)
        except Exception:
            sys.exit(f"HTTP {e.code} on {method} {url}")
    if not out.get("success", True):
        sys.exit(f"API error: {json.dumps(out.get('errors'), indent=2)}")
    return out


def _api(method: str, path: str, body: dict | None = None, params: str = "") -> dict:
    return _req(method, f"{API}{path}{params}", body)


def _zone_id(zone: str) -> str:
    if len(zone) == 32 and all(c in "0123456789abcdef" for c in zone):
        return zone
    res = _api("GET", "/zones", params=f"?name={zone}")
    if not res["result"]:
        sys.exit(f"zone not found: {zone}")
    return res["result"][0]["id"]


def cmd_verify(_: argparse.Namespace) -> None:
    res = _api("GET", "/user/tokens/verify")
    print(f"token OK — status: {res['result']['status']}")


def cmd_zones(_: argparse.Namespace) -> None:
    for z in _api("GET", "/zones")["result"]:
        plan = z.get("plan", {}).get("name", "?")
        print(f"{z['id']}  {z['name']:<30} {z['status']:<8} {plan}")


def cmd_dns(args: argparse.Namespace) -> None:
    zid = _zone_id(args.zone)
    recs = _api("GET", f"/zones/{zid}/dns_records", params="?per_page=200")["result"]
    for r in recs:
        proxied = "proxied" if r.get("proxied") else "dns-only"
        print(
            f"{r['id']}  {r['type']:<6} {r['name']:<40} {r['content']:<45} ttl={r['ttl']} {proxied}"
        )


def cmd_dns_add(args: argparse.Namespace) -> None:
    zid = _zone_id(args.zone)
    body = {
        "type": args.type,
        "name": args.name,
        "content": args.content,
        "ttl": args.ttl,
        "proxied": args.proxied,
    }
    r = _api("POST", f"/zones/{zid}/dns_records", body)["result"]
    print(f"created {r['id']}  {r['type']} {r['name']} -> {r['content']}")


def cmd_dns_update(args: argparse.Namespace) -> None:
    zid = _zone_id(args.zone)
    cur = _api("GET", f"/zones/{zid}/dns_records/{args.record_id}")["result"]
    body = {
        "type": args.type or cur["type"],
        "name": args.name or cur["name"],
        "content": args.content or cur["content"],
        "ttl": args.ttl if args.ttl is not None else cur["ttl"],
        "proxied": cur.get("proxied") if args.proxied is None else args.proxied,
    }
    r = _api("PUT", f"/zones/{zid}/dns_records/{args.record_id}", body)["result"]
    print(f"updated {r['id']}  {r['type']} {r['name']} -> {r['content']}")


def cmd_dns_del(args: argparse.Namespace) -> None:
    zid = _zone_id(args.zone)
    _api("DELETE", f"/zones/{zid}/dns_records/{args.record_id}")
    print(f"deleted {args.record_id}")


def cmd_analytics(args: argparse.Namespace) -> None:
    zid = _zone_id(args.zone)
    # Cloudflare analytics buckets are UTC days.
    since = (dt.datetime.now(tz=dt.UTC).date() - dt.timedelta(days=args.days - 1)).isoformat()
    query = """
    query($zoneTag: String!, $since: String!, $limit: Int!) {
      viewer { zones(filter: {zoneTag: $zoneTag}) {
        httpRequests1dGroups(limit: $limit, filter: {date_geq: $since},
                             orderBy: [date_DESC]) {
          dimensions { date }
          sum { requests cachedRequests bytes threats pageViews
                responseStatusMap { edgeResponseStatus requests } }
          uniq { uniques }
        } } }
    }"""
    out = _req(
        "POST",
        GRAPHQL,
        {
            "query": query,
            "variables": {"zoneTag": zid, "since": since, "limit": args.days},
        },
    )
    if out.get("errors"):
        sys.exit(f"GraphQL error: {json.dumps(out['errors'], indent=2)}")
    groups = out["data"]["viewer"]["zones"][0]["httpRequests1dGroups"]
    if not groups:
        print(f"no analytics data since {since}")
        return
    print(
        f"{'date':<12}{'requests':>10}{'cached%':>9}{'uniques':>9}"
        f"{'pageviews':>11}{'MB':>9}{'threats':>9}  errors(4xx/5xx)"
    )
    for g in groups:
        s, date = g["sum"], g["dimensions"]["date"]
        cached = 100 * s["cachedRequests"] / s["requests"] if s["requests"] else 0
        e4 = sum(
            m["requests"] for m in s["responseStatusMap"] if 400 <= m["edgeResponseStatus"] < 500
        )
        e5 = sum(m["requests"] for m in s["responseStatusMap"] if m["edgeResponseStatus"] >= 500)
        print(
            f"{date:<12}{s['requests']:>10}{cached:>8.1f}%{g['uniq']['uniques']:>9}"
            f"{s['pageViews']:>11}{s['bytes'] / 1e6:>9.1f}{s['threats']:>9}  {e4}/{e5}"
        )


def cmd_status_codes(args: argparse.Namespace) -> None:
    zid = _zone_id(args.zone)
    # Cloudflare analytics buckets are UTC days.
    since = (dt.datetime.now(tz=dt.UTC).date() - dt.timedelta(days=args.days - 1)).isoformat()
    query = """
    query($zoneTag: String!, $since: String!) {
      viewer { zones(filter: {zoneTag: $zoneTag}) {
        httpRequests1dGroups(limit: 31, filter: {date_geq: $since}) {
          sum { responseStatusMap { edgeResponseStatus requests } }
        } } }
    }"""
    out = _req("POST", GRAPHQL, {"query": query, "variables": {"zoneTag": zid, "since": since}})
    if out.get("errors"):
        sys.exit(f"GraphQL error: {json.dumps(out['errors'], indent=2)}")
    totals: dict[int, int] = {}
    for g in out["data"]["viewer"]["zones"][0]["httpRequests1dGroups"]:
        for m in g["sum"]["responseStatusMap"]:
            totals[m["edgeResponseStatus"]] = totals.get(m["edgeResponseStatus"], 0) + m["requests"]
    for code in sorted(totals):
        print(f"{code}  {totals[code]}")


def _account_id() -> str:
    res = _api("GET", "/accounts")["result"]
    if not res:
        sys.exit("no accounts visible to this token (add Account:Read permission)")
    return res[0]["id"]


def cmd_tunnels(_: argparse.Namespace) -> None:
    aid = _account_id()
    res = _api("GET", f"/accounts/{aid}/cfd_tunnel", params="?is_deleted=false")["result"]
    for t in res:
        conns = len(t.get("connections") or [])
        print(f"{t['id']}  {t['name']:<30} status={t['status']:<10} connections={conns}")


def cmd_purge(args: argparse.Namespace) -> None:
    zid = _zone_id(args.zone)
    body = {"files": args.urls} if args.urls else {"purge_everything": True}
    _api("POST", f"/zones/{zid}/purge_cache", body)
    print("cache purged: " + (f"{len(args.urls)} url(s)" if args.urls else "everything"))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("verify", help="verify the API token").set_defaults(fn=cmd_verify)
    sub.add_parser("zones", help="list zones").set_defaults(fn=cmd_zones)

    d = sub.add_parser("dns", help="list DNS records for a zone")
    d.add_argument("zone")
    d.set_defaults(fn=cmd_dns)

    da = sub.add_parser("dns-add", help="create a DNS record")
    da.add_argument("zone")
    da.add_argument("type", choices=["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "NS"])
    da.add_argument("name")
    da.add_argument("content")
    da.add_argument("--ttl", type=int, default=1, help="1 = auto")
    da.add_argument("--proxied", action="store_true")
    da.set_defaults(fn=cmd_dns_add)

    du = sub.add_parser("dns-update", help="update a DNS record (unset fields keep current)")
    du.add_argument("zone")
    du.add_argument("record_id")
    du.add_argument("--type")
    du.add_argument("--name")
    du.add_argument("--content")
    du.add_argument("--ttl", type=int)
    du.add_argument(
        "--proxied", type=lambda v: v.lower() == "true", default=None, metavar="true|false"
    )
    du.set_defaults(fn=cmd_dns_update)

    dd = sub.add_parser("dns-del", help="delete a DNS record")
    dd.add_argument("zone")
    dd.add_argument("record_id")
    dd.set_defaults(fn=cmd_dns_del)

    an = sub.add_parser("analytics", help="daily traffic for a zone (GraphQL)")
    an.add_argument("zone")
    an.add_argument("--days", type=int, default=7, choices=range(1, 32), metavar="1-31")
    an.set_defaults(fn=cmd_analytics)

    sc = sub.add_parser("status-codes", help="edge response status totals for a zone")
    sc.add_argument("zone")
    sc.add_argument("--days", type=int, default=7, choices=range(1, 32), metavar="1-31")
    sc.set_defaults(fn=cmd_status_codes)

    sub.add_parser("tunnels", help="list Cloudflare tunnels").set_defaults(fn=cmd_tunnels)

    pu = sub.add_parser("purge", help="purge zone cache (everything, or specific urls)")
    pu.add_argument("zone")
    pu.add_argument("urls", nargs="*", help="optional: specific URLs to purge")
    pu.set_defaults(fn=cmd_purge)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
