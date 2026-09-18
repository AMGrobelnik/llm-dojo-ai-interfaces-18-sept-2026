#!/usr/bin/env python
"""
Citation Verification Tool

Verify quoted citations against source URLs.

Usage:
    python aii_verify_quotes.py --text-file paper.txt

Citation format: ["quote"](https://example.com)
"""

import argparse
import re
import sys
from pathlib import Path

# Sibling module. These scripts are invoked by absolute path
# (`$PY $SKILL_DIR/scripts/<name>.py`), so Python puts this directory on
# sys.path itself and no path manipulation is needed.
from _wayback import snapshot_url

try:
    from aii_lib.abilities.aii_ability import aii_ability
except ImportError:  # standalone use: aii_lib / ability server not installed

    def aii_ability(*_args, **_kwargs):
        """No-op decorator fallback (the real one only attaches server metadata)."""

        def _decorator(func):
            return func

        return _decorator


SERVER_NAME = "aii_web_tools__verify_quotes"
DEFAULT_TIMEOUT = 120.0
SESSION_TIMEOUT = 120
POOL_CONNECTIONS = 50
POOL_MAXSIZE = 50


# =============================================================================
# Core Logic (used by server handler)
# =============================================================================

# Session pooling for connection reuse
_session = None


def init_verify_quotes():
    """Initialize verify quotes environment with warmup."""
    global _session
    import requests
    from requests.adapters import HTTPAdapter

    # Create session with connection pooling (pool_maxsize=50 for parallel requests)
    _session = requests.Session()
    adapter = HTTPAdapter(pool_maxsize=POOL_MAXSIZE, pool_connections=POOL_CONNECTIONS)
    _session.mount("https://", adapter)
    _session.mount("http://", adapter)
    _session.headers.update({"User-Agent": "Mozilla/5.0"})

    # Warmup
    try:
        _session.get("https://example.com", timeout=10)
    except Exception:
        pass


@aii_ability(
    name="aii_web_tools__verify_quotes",
    description="Verify quoted citations against source URLs.",
    venv="../../.ability_client_venv",
    requirements="server_requirements.txt",
    worker_init="init_verify_quotes",
)
def core_verify_quotes(text: str = "", citations: list[dict] | None = None) -> dict:
    """
    Verify citations in text against source URLs.

    Args:
        text: Text containing citations in format ["quote"](url)
        citations: Optional structured {quote, url} pairs, including quotes
            containing quotation marks or URLs containing parentheses.
            When provided, used instead of parsing text.

    Returns:
        Dict with success, counts, and citation verification results
    """
    global _session
    import fitz
    import html2text

    # Extract citations
    pattern = r'\["([^"]+)"\]\((https?://[^\)]+)\)'
    if citations is None:
        matches = re.findall(pattern, text)
    else:
        if not isinstance(citations, list) or any(
            not isinstance(cit, dict)
            or not isinstance(cit.get("quote"), str)
            or not cit["quote"].strip()
            or not isinstance(cit.get("url"), str)
            or not cit["url"].strip().startswith(("http://", "https://"))
            for cit in citations
        ):
            return {
                "success": False,
                "error": "citations must contain nonblank quote and HTTP(S) url strings",
            }
        matches = [(cit["quote"], cit["url"]) for cit in citations]

    if not matches:
        return {
            "success": False,
            "error": 'No citations found. Format: ["quote"](https://example.com)',
        }

    # Deduplicate
    seen = set()
    citations = []
    for quote, url in matches:
        key = (quote.strip(), url.strip())
        if key not in seen:
            seen.add(key)
            citations.append({"quote": quote.strip(), "url": url.strip()})

    def _extract(resp, url: str) -> str:
        """Turn a 200 response into searchable text."""
        content_type = resp.headers.get("content-type", "").lower()
        is_pdf = "pdf" in content_type or url.lower().endswith(".pdf")
        if is_pdf:
            doc = fitz.open(stream=resp.content, filetype="pdf")
            content = "\n".join(page.get_text() for page in doc)
            doc.close()
            return content
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(resp.text)

    def fetch_content(url: str) -> str | None:
        """Fetch a citation's text, falling back to the Wayback Machine.

        The status code is checked deliberately. Without that check a 403 or
        404 page was extracted like any other document, the quote was not
        found in it, and the citation was reported INVALID — which reads as
        "the author misquoted their source" when the truth is "nobody could
        open the source". Those two verdicts must not look alike.

        A page that is blocked, moved or dead today was usually fine when it
        was cited, and the archive still holds that version. Verifying the
        quote against it is the point: it answers the question actually being
        asked, which is whether the source ever said this.
        """
        try:
            resp = _session.get(url, allow_redirects=True, timeout=SESSION_TIMEOUT)
            if resp.status_code == 200:
                return _extract(resp, url)
        except Exception:
            resp = None

        try:
            archived = snapshot_url(url, session=_session)
            if not archived:
                return None
            arc_resp = _session.get(archived, allow_redirects=True, timeout=SESSION_TIMEOUT)
            if arc_resp.status_code != 200:
                return None
            return _extract(arc_resp, url)
        except Exception:
            return None

    def find_match(quote: str, content: str) -> str | None:
        quote_norm = " ".join(quote.split()).lower()
        content_norm = " ".join(content.split()).lower()
        idx = content_norm.find(quote_norm)
        if idx == -1:
            return None
        start = max(0, idx - 100)
        end = min(len(content_norm), idx + len(quote_norm) + 100)
        ctx = content_norm[start:end]
        if start > 0:
            ctx = "..." + ctx
        if end < len(content_norm):
            ctx = ctx + "..."
        return ctx

    # Verify each citation
    results = []
    valid_count = invalid_count = error_count = 0
    content_by_url = {}

    for cit in citations:
        if cit["url"] not in content_by_url:
            content_by_url[cit["url"]] = fetch_content(cit["url"])
        content = content_by_url[cit["url"]]
        if content is None:
            results.append(
                {
                    "quote": cit["quote"],
                    "source_url": cit["url"],
                    "status": "error",
                    "match_type": "none",
                    "error_message": "Failed to fetch URL",
                }
            )
            error_count += 1
        else:
            context = find_match(cit["quote"], content)
            if context:
                results.append(
                    {
                        "quote": cit["quote"],
                        "source_url": cit["url"],
                        "status": "valid",
                        "match_type": "exact",
                        "context": context,
                    }
                )
                valid_count += 1
            else:
                results.append(
                    {
                        "quote": cit["quote"],
                        "source_url": cit["url"],
                        "status": "invalid",
                        "match_type": "none",
                    }
                )
                invalid_count += 1

    return {
        "success": True,
        "total_citations": len(citations),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "error_count": error_count,
        "citations": results,
    }


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Verify citations against source URLs")
    parser.add_argument("--text-file", required=True, help="Path to text file with citations")
    args = parser.parse_args()

    try:
        text = Path(args.text_file).read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error: Failed to read file: {e}", file=sys.stderr)
        sys.exit(1)

    params = {"text": text}

    result = None
    try:
        from aii_lib.abilities.ability_server import call_server

        result = call_server(SERVER_NAME, params, timeout=DEFAULT_TIMEOUT)
    except Exception:
        result = None

    if result is None:
        # Standalone fallback: run the core logic locally (no ability server needed).
        init_verify_quotes()
        result = core_verify_quotes(**params)

    if result.get("success"):
        for idx, r in enumerate(result.get("citations", []), 1):
            if r.get("status") == "error":
                verdict = f"ERROR - {r.get('error_message', 'Unknown')}"
            elif r.get("status") == "valid":
                verdict = "VALID"
            else:
                verdict = "INVALID"
            print(f"Citation {idx}/{result['total_citations']}: {r['quote'][:60]}...")
            print(f"URL: {r['source_url']}")
            print(f"Verdict: {verdict}\n")
    else:
        print(f"Error: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
