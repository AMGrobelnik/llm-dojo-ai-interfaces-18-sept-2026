#!/usr/bin/env python3
"""Domain availability checker using RDAP + DNS fallback.

Usage:
    domain-check <keyword>                  # Check keyword across popular TLDs
    domain-check <domain1> <domain2> ...    # Check specific domains
    domain-check <keyword> --tlds com,io,ai # Check keyword with specific TLDs
    domain-check <keyword> --all            # Check all popular TLDs
"""

import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
END = "\033[0m"

# Popular TLDs to check by default
DEFAULT_TLDS = ["com", "io", "ai", "dev", "app", "co", "net", "org", "xyz", "tech"]
ALL_TLDS = [
    "com",
    "io",
    "ai",
    "dev",
    "app",
    "co",
    "net",
    "org",
    "xyz",
    "tech",
    "me",
    "cc",
    "gg",
    "so",
    "sh",
    "to",
    "is",
    "ly",
    "fm",
    "tv",
    "systems",
    "tools",
    "solutions",
    "studio",
    "cloud",
    "run",
    "science",
    "research",
    "engineering",
    "software",
    "digital",
    "world",
]

# RDAP bootstrap data (cached on first run)
_rdap_servers: dict[str, str] = {}


def load_rdap_bootstrap() -> dict[str, str]:
    """Load RDAP server mapping from IANA bootstrap file."""
    global _rdap_servers
    if _rdap_servers:
        return _rdap_servers

    cache_file = Path("/tmp/.rdap_bootstrap.json")
    # Cache for 24 hours
    if cache_file.exists():
        import time

        age = time.time() - cache_file.stat().st_mtime
        if age < 86400:
            _rdap_servers = json.loads(cache_file.read_text(encoding="utf-8"))
            return _rdap_servers

    try:
        req = Request(
            "https://data.iana.org/rdap/dns.json",
            headers={"User-Agent": "domain-check/1.0"},
        )
        # B310 audits the scheme: the IANA bootstrap url is the https literal above.
        with urlopen(req, timeout=10) as resp:  # nosec B310
            data = json.loads(resp.read())
        for entry in data["services"]:
            server = entry[1][0]
            for tld in entry[0]:
                _rdap_servers[tld] = server
        cache_file.write_text(json.dumps(_rdap_servers), encoding="utf-8")
    except Exception:
        pass

    return _rdap_servers


def check_rdap(domain: str, tld: str, servers: dict[str, str]) -> str | None:
    """Check domain via RDAP. Returns 'taken', 'available', or None (unsupported)."""
    server = servers.get(tld)
    if not server:
        return None

    url = f"{server.rstrip('/')}/domain/{domain}"
    if not url.startswith("https://"):
        return None  # RDAP servers are https by spec; anything else is not one
    try:
        req = Request(
            url,
            headers={
                "User-Agent": "domain-check/1.0",
                "Accept": "application/rdap+json",
            },
        )
        with urlopen(req, timeout=8):  # nosec B310  # scheme checked above
            return "taken"
    except HTTPError as e:
        if e.code == 404:
            return "available"
        if e.code == 429:
            return "rate_limited"
        return None
    except (URLError, TimeoutError, OSError):
        return None


def check_dns(domain: str) -> str:
    """Fallback: check if domain has NS records via dig."""
    try:
        result = subprocess.run(
            ["dig", "+short", "NS", domain],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip():
            return "taken"
        # No NS doesn't guarantee availability, but it's a signal
        # Also check A record
        result_a = subprocess.run(
            ["dig", "+short", "A", domain],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result_a.stdout.strip():
            return "taken"
        return "likely_available"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def check_domain(domain: str, servers: dict[str, str]) -> tuple[str, str]:
    """Check a single domain. Returns (domain, status)."""
    parts = domain.rsplit(".", 1)
    if len(parts) != 2:
        return (domain, "invalid")

    tld = parts[1]

    # Try RDAP first
    status = check_rdap(domain, tld, servers)
    if status:
        return (domain, status)

    # Fallback to DNS
    dns_status = check_dns(domain)
    return (domain, dns_status)


def parse_args(argv: list[str]) -> tuple[list[str], bool]:
    """Parse arguments. Returns (domains_to_check, json_output)."""
    if not argv:
        print(__doc__)
        sys.exit(1)

    json_output = "--json" in argv
    use_all = "--all" in argv
    argv = [a for a in argv if a not in ("--json", "--all")]

    # Check for --tlds flag
    tlds = DEFAULT_TLDS
    if "--tlds" in argv:
        idx = argv.index("--tlds")
        if idx + 1 < len(argv):
            tlds = argv[idx + 1].split(",")
            argv = argv[:idx] + argv[idx + 2 :]
        else:
            print("Error: --tlds requires a comma-separated list")
            sys.exit(1)

    if use_all:
        tlds = ALL_TLDS

    # If any arg contains a dot, treat all as full domain names
    if any("." in a for a in argv):
        domains = argv
    else:
        # Treat as keyword(s) and expand with TLDs
        keyword = argv[0]
        domains = [f"{keyword}.{tld}" for tld in tlds]

    return domains, json_output


def main():
    domains, json_output = parse_args(sys.argv[1:])
    servers = load_rdap_bootstrap()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_domain, domain, servers): domain for domain in domains}
        for future in concurrent.futures.as_completed(futures):
            domain, status = future.result()
            results.append((domain, status))

    # Sort by original order
    results.sort(key=lambda x: domains.index(x[0]))

    if json_output:
        print(json.dumps([{"domain": d, "status": s} for d, s in results], indent=2))
        return

    # Pretty print
    max_len = max(len(d) for d, _ in results) if results else 0

    available = []
    taken = []
    uncertain = []

    for domain, status in results:
        padded = domain.ljust(max_len + 2)
        if status == "available":
            print(f"  {GREEN}✓ {padded}{BOLD}AVAILABLE{END}")
            available.append(domain)
        elif status == "likely_available":
            print(f"  {YELLOW}? {padded}LIKELY AVAILABLE {DIM}(no RDAP, DNS negative){END}")
            uncertain.append(domain)
        elif status == "taken":
            print(f"  {RED}✗ {padded}{DIM}taken{END}")
            taken.append(domain)
        elif status == "rate_limited":
            print(f"  {YELLOW}! {padded}rate limited{END}")
            uncertain.append(domain)
        else:
            print(f"  {DIM}? {padded}{status}{END}")
            uncertain.append(domain)

    # Summary
    print()
    total = len(results)
    print(f"  {CYAN}{len(available)}/{total} available{END}", end="")
    if uncertain:
        print(f"  {YELLOW}{len(uncertain)} uncertain{END}", end="")
    print()


if __name__ == "__main__":
    main()
