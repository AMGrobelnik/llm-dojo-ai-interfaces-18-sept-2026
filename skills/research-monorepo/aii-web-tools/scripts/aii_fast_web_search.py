#!/usr/bin/env python
"""
Fast Web Search Tool — two modes, free-first, Serper as the paid last resort.

Two selectable modes (``--mode``, default ``general``):

  general    General web, walked in order (only engines that are configured):
               keyless-unlimited:  searxng (optional, FIRST if SEARXNG_URL set) -> ddgs -> marginalia
               recurring-free keyed: exa -> linkup -> tavily
  scholarly  Academic works via keyless APIs, walked in order:
               OpenAlex -> Crossref

Both fall back to Serper.dev (Google, paid ~$0.001/query) ONLY when every free
engine in the chosen mode is down or empty. Every engine is normalized to the
same ``{title, link, snippet}`` shape; the result reports the exact ``source``
that served it and the real ``cost_usd`` ($0 for the free engines, the Serper
credit cost otherwise) — so the run's cost ledger names the provider actually
used and its true cost.

Why this ordering (measured 2026-08-05, incl. live datacenter-IP soaks):
  * ddgs is the free workhorse and answers first in practice. Its backends
    yandex/bing/brave go out through primp (a real-browser TLS fingerprint), so —
    unlike raw scrapers — they are NOT CAPTCHA-blocked from a datacenter IP: soaks
    on the RunPod pod returned ~100% with zero decay. ddgs (9.14.4) tries the list
    in fixed order, so ``_ddgs`` shuffles it per call to spread load across the
    three and multiply sustained volume before any one rate-limits. On-pod re-check:
    yandex/bing/brave work; yahoo went flaky and startpage/duckduckgo/google/mojeek
    returned nothing; note ``mullvad``/``auto`` are not real ddgs backends (it
    silently falls back to default), so only the three real working ones are pinned.
  * searxng and marginalia are $0/keyless but query public engines directly
    (no TLS-fingerprint client), so from a datacenter IP they are blocked/thin.
    searxng is opt-in only (SEARXNG_URL, OFF by default — we run no instance;
    public ones are 429 / JSON-disabled); marginalia is a niche independent index
    kept as a supplement.
  * recurring-free keyed tiers (exa $10/mo, linkup ~$5-20/mo, tavily 1k/mo — all
    no-card, monthly-renewing) are official APIs, so they are IMMUNE to the
    datacenter-IP blocking and act as the reliable free workhorses. Placed after
    the keyless layer to preserve their monthly quota. Each is included only when
    its key is set.
  * Serper is paid last resort — its "free" tier is a one-time trial, so it does
    not count as free.

This skill is used by the OpenHands agent backends (free + paid). The Claude
agent has its own native web search and never calls this skill.

Usage:
    python aii_fast_web_search.py --query "kubernetes hpa best practices"
    python aii_fast_web_search.py -q "mixture of experts" --mode scholarly -n 5
"""

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[4] / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


SERVER_NAME = "aii_web_tools__search"
# DEFAULT_TIMEOUT is the OUTER cap on the whole call_server round-trip — it must
# cover the full free-first chain (several providers, each capped at 10s below),
# so it is deliberately NOT a per-provider wait.
DEFAULT_TIMEOUT = 120.0
SESSION_TIMEOUT = 10  # per-provider cap for the Serper (paid last-resort) request
POOL_CONNECTIONS = 50
POOL_MAXSIZE = 50

# Browser UA for the keyless scrapers — marginalia and the ddgs backends serve a
# default python-requests UA thin or empty results.
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
# Uniform 10s per-provider cap: a healthy engine answers in ~1-2s, so 10s is a
# generous "hung vs slow" ceiling — it fails a blocked provider over to the next
# without cutting off a slow-but-valid response. Shared by searxng/marginalia and
# the keyed tiers (exa/linkup/tavily) + the scholarly APIs (openalex/crossref).
# It is the CEILING, not the value every attempt gets: the walk clips each one
# to what remains of the single budget, so a late provider is given less.
_FREE_TIMEOUT = 10.0
# The least time an attempt needs to be worth starting. A healthy engine answers
# in ~1-2s, so 3s clears that with margin while still refusing the sliver at the
# end of a walk — starting a provider with 0.4s left cannot produce an answer and
# only delays the error the caller is waiting for.
_MIN_ATTEMPT_SECONDS = 3.0
# ddgs tries these backends in the ORDER GIVEN, first non-empty wins — it does NOT
# randomize, so ``_ddgs`` shuffles the order per call to spread load evenly across
# the pool (each backend leads ~1/N of the time instead of one always taking the
# hit), which multiplies the sustained volume before any single backend rate-limits
# and adds redundancy if one gets blocked. These are the real ddgs (9.14.4) text
# backends that work from a datacenter IP: yandex/bing/brave each served under an
# on-pod soak; yahoo went flaky and startpage/duckduckgo/google/mojeek returned
# nothing. NB: an unrecognised backend name (e.g. "mullvad", "auto") is NOT an
# error — ddgs silently falls back to its default engine — so only real, validated
# backends belong here. 10s per-backend cap (uniform with the rest): long enough
# for a slow-but-working backend, short enough that a blocked one fails over fast.
_DDGS_BACKENDS = ("yandex", "bing", "brave")
_DDGS_TIMEOUT = 10

# --- Keys / endpoints --------------------------------------------------------
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
EXA_API_KEY = os.environ.get("EXA_API_KEY", "")
LINKUP_API_KEY = os.environ.get("LINKUP_API_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
# Optional self-hosted SearXNG base URL — tried FIRST in the general chain when
# set. OFF by default: we run no SearXNG instance (from a datacenter IP its
# scraper engines are CAPTCHA-blocked, so it adds nothing ddgs does not already
# cover). Point it at a reachable instance to enable it as the first hop.
SEARXNG_URL = os.environ.get("SEARXNG_URL", "")


def _free_tools_enabled() -> bool:
    """True on a $0 free-pool run: the backend sets ``AII_FREE_TOOLS=1`` to steer
    cost-bearing skills onto their free path (see ``aii_lib.run_cost``). When set,
    the paid Serper last resort is skipped and the free-source failure is surfaced
    instead, so a nominally-$0 run can never be billed. Mirrors the sibling
    cost-bearing skills that share this env contract.
    """
    return os.environ.get("AII_FREE_TOOLS", "").strip().lower() in ("1", "true", "yes", "on")


# Session pooling for connection reuse across the HTTP-based engines.
HTTP_SESSION = None

# --- Cost accounting ---------------------------------------------------------
# Only Serper bills per call: 1 credit for <=10 results, 2 above, at the
# conservative $0.001/credit Starter rate. Every free engine is a hard $0
# (keyless, or a monthly-renewing no-card free tier).
SERPER_USD_PER_CREDIT = 0.001


def http_client():
    """Pooled session if ``init_web_search`` ran, else the bare requests module.

    Both expose ``.get``/``.post``; the free engines and Serper all go through
    this so connection reuse kicks in inside a worker without any of them
    depending on the session existing.
    """
    if HTTP_SESSION is not None:
        return HTTP_SESSION
    import requests

    return requests


# =============================================================================
# GENERAL-WEB engines (mode="general")
# =============================================================================
# -- keyless, unlimited --------------------------------------------------------
def _searxng(query: str, n: int, timeout: float = _FREE_TIMEOUT) -> list[dict]:
    """Self-hosted SearXNG JSON API (opt-in via SEARXNG_URL). Keyless, unlimited,
    aggregates Google/Bing/etc. Needs a reachable instance with json in
    search.formats and the limiter disabled."""
    r = http_client().get(
        f"{SEARXNG_URL.rstrip('/')}/search",
        params={"q": query, "format": "json", "language": "en", "safesearch": 0},
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    r.raise_for_status()
    return [
        {"title": w.get("title", ""), "link": w.get("url", ""), "snippet": w.get("content", "")}
        for w in (r.json().get("results") or [])[:n]
    ]


def _ddgs(query: str, n: int, timeout: float = _DDGS_TIMEOUT) -> list[dict]:
    """General web via the keyless ``ddgs`` library. Shuffle the backend order per
    call (ddgs itself does not) so no single backend is always tried first — load
    spreads evenly across the pool; the first non-empty backend wins.

    ``timeout`` is the budget for the WHOLE call, so it is divided by the backend
    count: ddgs applies its scalar per request and walks the backends in
    sequence, so passing the budget undivided would let one call take N times
    it — the arithmetic the walk budget exists to stop, reproduced one level
    down."""
    import random

    from ddgs import DDGS

    backends = ", ".join(random.sample(_DDGS_BACKENDS, len(_DDGS_BACKENDS)))
    out = DDGS(timeout=timeout / len(_DDGS_BACKENDS)).text(query, max_results=n, backend=backends)
    return [
        {
            "title": r.get("title", ""),
            "link": r.get("href") or r.get("url", ""),
            "snippet": r.get("body", ""),
        }
        for r in out
    ]


def _marginalia(query: str, n: int, timeout: float = _FREE_TIMEOUT) -> list[dict]:
    """Marginalia's keyless public API — an independent index strong on technical
    / long-form pages. ~20 results, no key."""
    r = http_client().get(
        f"https://api.marginalia.nu/public/search/{quote(query)}",
        headers={"User-Agent": _UA, "Accept": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return [
        {"title": w.get("title", ""), "link": w.get("url", ""), "snippet": w.get("description", "")}
        for w in (r.json().get("results") or [])[:n]
    ]


# -- recurring-free keyed tiers (official APIs — datacenter-IP-immune) ---------
def _exa(query: str, n: int, timeout: float = _FREE_TIMEOUT) -> list[dict]:
    """Exa neural search — recurring-free ($10/mo credit, no card)."""
    r = http_client().post(
        "https://api.exa.ai/search",
        json={
            "query": query,
            "numResults": n,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 300}},
        },
        headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return [
        {
            "title": w.get("title", ""),
            "link": w.get("url", ""),
            "snippet": (w.get("text") or "")[:300],
        }
        for w in (r.json().get("results") or [])[:n]
    ]


def _linkup(query: str, n: int, timeout: float = _FREE_TIMEOUT) -> list[dict]:
    """Linkup search — recurring-free (~$5-20/mo credit topped up monthly, no card)."""
    r = http_client().post(
        "https://api.linkup.so/v1/search",
        json={"q": query, "depth": "standard", "outputType": "searchResults"},
        headers={"Authorization": f"Bearer {LINKUP_API_KEY}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return [
        {
            "title": w.get("name", ""),
            "link": w.get("url", ""),
            "snippet": (w.get("content") or "")[:300],
        }
        for w in (r.json().get("results") or [])[:n]
    ]


def _tavily(query: str, n: int, timeout: float = _FREE_TIMEOUT) -> list[dict]:
    """Tavily search — recurring-free (1000 credits/mo, no card)."""
    r = http_client().post(
        "https://api.tavily.com/search",
        json={"query": query, "max_results": n, "search_depth": "basic"},
        headers={"Authorization": f"Bearer {TAVILY_API_KEY}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return [
        {
            "title": w.get("title", ""),
            "link": w.get("url", ""),
            "snippet": (w.get("content") or "")[:300],
        }
        for w in (r.json().get("results") or [])[:n]
    ]


# =============================================================================
# SCHOLARLY engines (mode="scholarly") — keyless, $0
# =============================================================================
def _polite_contact() -> str:
    """Contact for OpenAlex/Crossref's "polite pool", or ``""``.

    Read from the environment rather than hardcoded: the deployment's own
    address is private (the repo's gitleaks config rejects that domain in
    tracked code, correctly — this skill ships in the public export). Both APIs
    work without it; supplying one only buys the higher polite-pool rate limit,
    so an unset var degrades throughput, never correctness.
    """
    return os.environ.get("AII_POLITE_CONTACT", "").strip()


def _polite_params(extra: dict) -> dict:
    """``extra`` plus ``mailto`` when a contact is configured."""
    contact = _polite_contact()
    return {**extra, "mailto": contact} if contact else dict(extra)


def _openalex(query: str, n: int, timeout: float = _FREE_TIMEOUT) -> list[dict]:
    r = http_client().get(
        "https://api.openalex.org/works",
        params=_polite_params({"search": query, "per-page": min(n, 25)}),
        timeout=timeout,
    )
    r.raise_for_status()
    out = []
    for w in (r.json().get("results") or [])[:n]:
        loc = (w.get("primary_location") or {}).get("source") or {}
        bits = [b for b in (loc.get("display_name"), str(w.get("publication_year") or "")) if b]
        cited = w.get("cited_by_count")
        if cited is not None:
            bits.append(f"cited by {cited}")
        out.append(
            {
                "title": w.get("title") or "",
                "link": w.get("doi") or w.get("id") or "",
                "snippet": " · ".join(bits),
            }
        )
    return out


def _crossref(query: str, n: int, timeout: float = _FREE_TIMEOUT) -> list[dict]:
    r = http_client().get(
        "https://api.crossref.org/works",
        params=_polite_params({"query": query, "rows": min(n, 20)}),
        timeout=timeout,
    )
    r.raise_for_status()
    out = []
    for w in ((r.json().get("message") or {}).get("items") or [])[:n]:
        title = (w.get("title") or [""])[0]
        container = (w.get("container-title") or [""])[0]
        # Crossref emits date-parts as [[YYYY,...]], but also [[None]] (no date)
        # and even [[]] (empty inner) — guard both so one dateless record cannot
        # raise IndexError and abort the whole result set.
        dp = ((w.get("issued") or {}).get("date-parts") or [[None]])[0]
        year = dp[0] if dp else None
        bits = [b for b in (container, str(year) if year else "") if b]
        out.append({"title": title, "link": w.get("URL") or "", "snippet": " · ".join(bits)})
    return out


def _general_chain() -> tuple:
    """The general free-first chain, in order, including only CONFIGURED engines:
    keyless-unlimited first (searxng self-host, ddgs, marginalia), then the
    recurring-free keyed tiers (exa, linkup, tavily) whose key is set. Serper
    (paid) is appended by ``core_web_search`` as the last resort, not here.
    """
    chain: list[tuple] = []
    if SEARXNG_URL:
        chain.append(("searxng", _searxng))
    chain.append(("ddgs", _ddgs))
    chain.append(("marginalia", _marginalia))
    if EXA_API_KEY:
        chain.append(("exa", _exa))
    if LINKUP_API_KEY:
        chain.append(("linkup", _linkup))
    if TAVILY_API_KEY:
        chain.append(("tavily", _tavily))
    return tuple(chain)


# Free engines per mode; walked in order, first non-empty wins. ``general`` is
# resolved from the configured engines at import; ``scholarly`` is fixed.
MODES = {
    "general": _general_chain(),
    "scholarly": (("openalex", _openalex), ("crossref", _crossref)),
}
DEFAULT_MODE = "general"


def free_web_search(
    query: str, max_results: int, mode: str = DEFAULT_MODE, budget_seconds: float | None = None
) -> dict:
    """Walk the free engines for ``mode`` (first non-empty wins, $0).

    ``core_web_search`` calls this first and adds the Serper fallback; the result
    shape mirrors ``core_web_search``'s.
    """
    chain = MODES.get(mode)
    if chain is None:
        return {"success": False, "error": f"unknown mode {mode!r}; expected {sorted(MODES)}"}
    errors = []
    # One wall-clock bound for the WHOLE walk, not per provider. The chain is up
    # to six entries at ~10 s, ddgs alone walks three backends, and requests
    # applies a scalar timeout separately to connect AND read — so the walk's
    # arithmetic worst case runs past the DEFAULT_TIMEOUT that :76-78 says must
    # cover it. Past that point the caller (``call_server(..., timeout=
    # DEFAULT_TIMEOUT)``) has already given up, so every further provider is
    # work nobody will read; stopping turns that into an answer that names the
    # budget instead of a bare transport timeout upstream.
    # ``budget_seconds`` lets the caller hand down what is left of a budget it
    # already owns, so the free walk and the paid last resort share ONE bound
    # instead of stacking two. ``is None`` rather than ``or``: a caller that has
    # 0s left means 0s, and must not silently be given the full default.
    budget = DEFAULT_TIMEOUT if budget_seconds is None else budget_seconds
    deadline = time.monotonic() + budget
    for name, fn in chain:
        # Clip this attempt to what the walk has left, and refuse one that
        # cannot finish. A deadline alone only stops the walk BETWEEN
        # providers: an attempt begun a moment under it still runs its own
        # full timeout past it, which is how the walk overran the budget it
        # was given. ddgs is the reason the floor is not merely cosmetic — it
        # walks three backends, so its scalar is divided by that count and a
        # sliver of remaining time buys an attempt too short to return.
        remaining = deadline - time.monotonic()
        if remaining < _MIN_ATTEMPT_SECONDS:
            errors.append(
                f"{name}: skipped — {remaining:.0f}s left of the {budget:.0f}s walk "
                f"budget, under the {_MIN_ATTEMPT_SECONDS:.0f}s an attempt needs"
            )
            continue
        try:
            results = [
                r
                for r in fn(query, max_results, min(_FREE_TIMEOUT, remaining))
                if r.get("link") and r.get("title")
            ]
        except Exception as e:  # network, rate limit, quota, schema drift
            errors.append(f"{name}: {type(e).__name__}")
            continue
        if results:
            return {
                "success": True,
                "query": query,
                "count": len(results),
                "results": results[:max_results],
                # ``source`` = the exact engine that answered; ``billing`` says
                # WHY the cost is $0, which a bare 0.00 cannot.
                "source": name,
                "mode": mode,
                "billing": "free",
                "cost_usd": 0.0,
            }
        errors.append(f"{name}: no results")
    return {"success": False, "error": f"all free {mode} sources failed: " + "; ".join(errors)}


def serper_cost_usd(max_results: int) -> float:
    """USD for one Serper search of ``max_results`` results (credit-based)."""
    n_credits = 1 if max_results <= 10 else 2
    return round(n_credits * SERPER_USD_PER_CREDIT, 6)


def record_external_cost(cost_usd, *, tool: str, **meta) -> None:
    """Append this call's $ to the per-task cost ledger (``AII_COST_LEDGER``).

    No-op when the env var is unset (standalone use) or cost is missing.
    Best-effort — a telemetry write must never break the tool's real result.
    The agent backend that spawned this subprocess reads the ledger back at
    summary time and folds the total into the run's external_tool_cost.
    """
    ledger = os.environ.get("AII_COST_LEDGER")
    if not ledger or cost_usd is None:
        return
    import json as _json
    import time as _time

    rec = {"ts": _time.time(), "tool": tool, "cost_usd": float(cost_usd), **meta}
    try:
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec) + "\n")
    except OSError:
        pass


def init_web_search():
    """Create a pooled HTTP session for connection reuse across the engines.

    No Serper key is baked into the shared session (it would be sent to the free
    engines too) and no warmup request is made — the old Serper warmup billed a
    credit per worker init for a backstop free-first now rarely reaches.
    """
    global HTTP_SESSION
    import requests
    from requests.adapters import HTTPAdapter

    HTTP_SESSION = requests.Session()
    adapter = HTTPAdapter(pool_maxsize=POOL_MAXSIZE, pool_connections=POOL_CONNECTIONS)
    HTTP_SESSION.mount("https://", adapter)
    HTTP_SESSION.mount("http://", adapter)


def _serper(query: str, max_results: int, timeout: float = SESSION_TIMEOUT) -> dict:
    """Serper.dev (Google) — the paid last resort. Key passed per-call, never
    baked into the shared session.

    ``timeout`` is clipped by the caller to what remains of the one budget the
    whole search owns: this is the only paid call here, so letting it run past
    a deadline the caller has already abandoned spends money on an answer
    nobody receives."""
    resp = http_client().post(
        "https://google.serper.dev/search",
        json={"q": query, "num": max_results},
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        # Surface the upstream body. Serper returns an actionable message
        # (e.g. {"message": "Not enough credits"}) a bare status code hides.
        detail = resp.text[:300]
        try:
            detail = resp.json().get("message", detail)
        except ValueError:
            pass
        return {"success": False, "error": f"HTTP {resp.status_code}: {detail}"}
    results = [
        {"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in resp.json().get("organic", [])[:max_results]
    ]
    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "source": "serper",
        "billing": "paid",
        # Self-reported external API cost (Serper credits). Single source of
        # truth for this call's $ — recorded into the run's cost ledger by main.
        "cost_usd": serper_cost_usd(max_results),
    }


@aii_ability(
    name="aii_web_tools__search",
    description=(
        "Search the web free-first. mode='general' (default): free general "
        "engines (searxng/ddgs/marginalia + exa/linkup/tavily); mode='scholarly': "
        "OpenAlex/Crossref. Serper (paid) is the last resort when the free engines miss."
    ),
    check_env="check_env.sh",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_web_search",
    # The free-first walk ends at Serper, which BILLS (~$0.001/query), so a
    # blanket retry re-runs the whole walk and buys a second credit. It fires
    # in practice: this handler returns the error as a STRING, and a
    # ReadTimeout stringifies containing "Read timed out", which the worker
    # counts as transient. record_external_cost runs once in main(), so the
    # ledger books one credit for up to four searches.
    retries=0,
)
def core_web_search(query: str = "", max_results: int = 10, mode: str = DEFAULT_MODE) -> dict:
    """Free-first web search with two selectable modes.

    Walks the free engines for ``mode`` (general: keyless scrapers then the
    recurring-free keyed tiers; scholarly: OpenAlex -> Crossref); the first to
    return results wins at $0. Only when all of them are down or empty does it
    fall back to Serper (paid, ~$0.001/query). Every result carries ``source``
    (the engine that answered), ``mode``, and ``cost_usd``.

    Args:
        query: Search query string.
        max_results: Maximum number of results (default 10, max 100).
        mode: "general" (default) or "scholarly".

    Returns:
        Dict with success, query, count, results ``[{title, link, snippet}]``,
        source, mode, billing, and cost_usd.
    """
    if not query or not query.strip():
        return {
            "success": False,
            "error": "Search query is required (got empty or missing 'query' parameter)",
        }
    if len(query) > 2000:
        return {"success": False, "error": f"Query too long ({len(query)} chars, max 2000)"}
    if mode not in MODES:
        return {"success": False, "error": f"unknown mode {mode!r}; expected {sorted(MODES)}"}

    max_results = min(max(1, max_results), 100)

    # ONE budget for the whole search — the free walk AND the paid last resort
    # together — because the caller applies a single ``call_server(...,
    # timeout=DEFAULT_TIMEOUT)`` to all of it. Giving each stage its own full
    # timeout stacks them: a free walk that used its whole budget followed by a
    # Serper attempt runs past the point the caller gave up, and the Serper leg
    # is the one that costs money.
    deadline = time.monotonic() + DEFAULT_TIMEOUT

    # Free engines for the chosen mode first — keyless / recurring-free, $0.
    # Serper is the last resort, reached only when all of them are down or empty.
    free_result = free_web_search(
        query, max_results, mode, budget_seconds=deadline - time.monotonic()
    )
    if free_result.get("success"):
        return free_result

    # No Serper key, or a $0 free-pool run (AII_FREE_TOOLS=1) that must never be
    # billed -> nothing paid left to try; surface the free-source failure.
    if not SERPER_API_KEY or _free_tools_enabled():
        return free_result

    if HTTP_SESSION is None:
        init_web_search()
    remaining = deadline - time.monotonic()
    if remaining < _MIN_ATTEMPT_SECONDS:
        # Extend the existing ``error`` STRING rather than inventing an
        # ``errors`` list: the free-walk failure shape is a single string, and a
        # key nothing reads would drop this silently.
        free_result["error"] = (
            f"{free_result.get('error', 'free sources failed')}; serper: skipped — "
            f"{remaining:.0f}s left of the {DEFAULT_TIMEOUT:.0f}s search budget, under the "
            f"{_MIN_ATTEMPT_SECONDS:.0f}s an attempt needs"
        )
        return free_result
    try:
        out = _serper(query, max_results, min(SESSION_TIMEOUT, remaining))
    except Exception as e:  # network etc. — report, don't crash the caller
        return {"success": False, "error": f"serper: {type(e).__name__}: {e}", "query": query}
    out.setdefault("mode", mode)
    return out


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Free-first web search (general or scholarly mode, Serper fallback)"
    )
    parser.add_argument("--query", "-q", required=True, help="Search query")
    parser.add_argument("--max-results", "-n", type=int, default=10)
    parser.add_argument(
        "--mode",
        "-m",
        choices=sorted(MODES),
        default=DEFAULT_MODE,
        help="general (default): free general engines; scholarly: OpenAlex/Crossref",
    )
    args = parser.parse_args()

    params = {"query": args.query, "max_results": args.max_results, "mode": args.mode}

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME, params, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None

    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        init_web_search()
        result = core_web_search(**params)

    if result.get("success"):
        # Record this call's external API $ into the agent's per-task cost
        # ledger (no-op when standalone). ``source`` names the exact provider
        # that served it so the ledger shows which engine was used and its cost.
        record_external_cost(
            result.get("cost_usd"),
            tool=SERVER_NAME,
            source=result.get("source", ""),
            mode=result.get("mode", ""),
            query=result.get("query", ""),
            count=result.get("count", 0),
        )
        print(
            f"Search: {result['query']}  [{result.get('mode', '?')} via {result.get('source', '?')}]"
        )
        print(f"Found: {result['count']} results\n")
        for i, r in enumerate(result.get("results", []), 1):
            print(f"{i}. {r['title']}")
            print(f"   {r['link']}")
            if r.get("snippet"):
                print(f"   {r['snippet'][:200]}...")
            print()
    else:
        print(f"Error: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
