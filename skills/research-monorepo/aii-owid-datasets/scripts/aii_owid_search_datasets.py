#!/usr/bin/env python
"""
OWID Table Search Tool

Search for tables in Our World in Data catalog.

Usage:
    python aii_owid_search_datasets.py "renewable energy" --limit 5
"""

import argparse
import sys

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


SERVER_NAME = "aii_owid_datasets__search_datasets"
DEFAULT_LIMIT = 3


# =============================================================================
# Core Logic (used by server handler)
# =============================================================================


def init_owid_search():
    """Warm the OWID catalog frame so the first real query isn't the slow one.

    ``catalog.search`` pulls and caches the catalog index on first use — 5.3 s
    measured cold, negligible after. Doing that at worker init keeps the cost
    off the agent's first call.

    Deliberately does NOT catch. This used to end in ``except Exception: pass``
    to avoid "stopping the worker from starting", but the ability worker
    already guarantees that and does far more with the error:
    ``agent_abilities/worker.py::_run_worker_init`` catches it itself, logs the
    traceback, writes a crash log, remembers it as ``init_error``, RETRIES init
    on the next incoming request so a transient failure self-heals, and returns
    the cause to the caller instead of letting it vanish.

    Swallowing it here defeated every one of those. A warmup that failed was
    recorded as a SUCCESS, so the worker never retried init and never
    self-healed — it just kept serving from whatever half-initialised state the
    failed warmup left behind, for the rest of that worker's life. Letting the
    exception out is both less code and strictly more robust.
    """
    import os

    from owid import catalog

    os.environ["TQDM_DISABLE"] = "1"
    catalog.search("test", kind="table", limit=1)


@aii_ability(
    name="aii_owid_datasets__search_datasets",
    description="Search Our World in Data catalog for tables by keyword.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_owid_search",
)
def core_owid_search(query: str = "", limit: int = 3) -> dict:
    """Search OWID tables by keyword.

    Uses ``owid.catalog.search`` — the library's own index — rather than a
    local BM25 index. The previous implementation loaded ``_index/`` from
    disk, but that artifact was never committed and nothing builds it, so
    EVERY call returned "Index not found": 932 of them on one production
    server, 100% failing, while the download ability's error text sends
    agents here to look up paths. ``owid-catalog`` is pinned >=0.4.0 and
    ships 1.1.0, which both removed the 0.x ``RemoteCatalog`` the old
    builder would have used and added this search — so the index was
    obsolete, not merely missing.

    Args:
        query: Search query string
        limit: Maximum number of results (default: 3)

    Returns:
        Dict with success status and a formatted result string.
    """
    import os

    os.environ["TQDM_DISABLE"] = "1"

    if not query:
        return {"success": False, "error": "query is required"}

    try:
        from owid import catalog

        # Slice locally: ``catalog.search``'s own ``limit=`` is accepted but
        # NOT honoured in owid-catalog 1.2.4 — measured on the deployed pod,
        # limit=1, limit=3 and limit=10 all return the same 84 rows for
        # "gdp". Without this slice the agent asks for 3 tables and gets
        # every match, each rendered with path/title/description/columns,
        # which floods its context.
        results = list(catalog.search(query, kind="table", limit=limit))[:limit]
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}

    if not results:
        return {"success": True, "result": f"No OWID tables found for '{query}'."}

    lines = [f"Found {len(results)} OWID tables for '{query}':\n"]
    for i, r in enumerate(results, start=1):
        get = r.__dict__.get
        lines.append(f"[{i}] {get('title') or get('table') or 'Unknown'}")
        lines.append(f"    Path: {get('path') or ''}")
        desc = get("description") or ""
        if desc:
            lines.append(f"    Description: {desc[:200] + '...' if len(desc) > 200 else desc}")
        ns, ds, ver = get("namespace"), get("dataset"), get("version")
        if ns or ds or ver:
            lines.append(f"    Source: {ns or '?'}/{ds or '?'} ({ver or 'no version'})")
        # ``dimensions`` is the column list. It replaces the old per-variable
        # block (name/unit/description): the catalog search result carries no
        # variable metadata, so that detail is genuinely unavailable here
        # rather than dropped for brevity. Download the table for the rest.
        dims = get("dimensions") or []
        if dims:
            lines.append(f"    Columns ({len(dims)}): {', '.join(map(str, dims[:20]))}")
        fmts = get("formats") or []
        if fmts:
            lines.append(f"    Formats: {', '.join(map(str, fmts))}")
        lines.append("")

    return {"success": True, "result": "\n".join(lines)}


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Search OWID tables")
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Number of results (default: 3)",
    )
    args = parser.parse_args()

    params = {
        "query": args.query,
        "limit": args.limit,
    }

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME, params, timeout=60.0)
    except Exception:
        result = None

    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        init_owid_search()
        result = core_owid_search(**params)

    if isinstance(result, dict):
        if result.get("success"):
            print(result.get("result", ""))
        else:
            print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    else:
        print(result)


if __name__ == "__main__":
    main()
