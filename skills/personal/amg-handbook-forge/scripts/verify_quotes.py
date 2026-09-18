#!/usr/bin/env python3
"""Re-verify every verbatim quote in a generated handbook bundle.

MODIFIED COPY of aii-web-tools/scripts/aii_verify_quotes.py — same extraction
pipeline (requests session + PyMuPDF for PDFs + html2text for HTML), which is
what the harvest itself reads pages through, so verification sees the page
EXACTLY as the miner did. Forge extensions on top of the original:
  * collects from the whole bundle: ["quote"](url) quote-links in any *.md
    PLUS SOURCES.md table rows (scheme-less URLs supported)
  * conservative normalization (curly quotes/dashes/ellipses/markdown
    presentation/punct-spacing — never word changes) + elided-quote segments
  * verdicts OK / SOFT-MISS / FETCH-FAIL (+ arXiv pdf→abs fallback), JSON
    report, exit codes for CI-style gating
  * auto re-exec into the aii-web-tools ability venv when deps are absent

Usage:  python3 verify_quotes.py <bundle-dir> [--timeout 30] [--json out.json]
Exit:   0 all verified · 1 any SOFT-MISS / FETCH-FAIL (resolve or demote)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

VENV_PY = Path(__file__).resolve().parents[2] / ".ability_client_venv/bin/python"
try:
    import fitz  # pymupdf
    import html2text
    import requests
except ImportError:  # re-exec with the aii-web-tools venv (the harvest pipeline)
    if VENV_PY.exists() and os.environ.get("_VQ_REEXEC") != "1":
        os.environ["_VQ_REEXEC"] = "1"
        os.execv(str(VENV_PY), [str(VENV_PY), *sys.argv])  # noqa: S606 — intentional shell-less re-exec into the pinned ability venv
    print("ERROR: requests+pymupdf+html2text unavailable and no ability venv found")
    raise SystemExit(2) from None  # explicit raise so type-checkers see the branch terminate

QUOTE_LINK = re.compile(r"\[[“\"]([^\"“”]{15,}?)[”\"]\]\((https?://[^)\s]+)\)", re.S)
TABLE_URL = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}/[^\s|)\]>]*[^\s|)\]>.,]")
TABLE_QUOTE = re.compile(r"[\"“](.{15,}?)[\"”]", re.S)
MIN_LEN = 15

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
fitz.TOOLS.mupdf_display_errors(False)


def fetch_content(url: str, timeout: int) -> tuple[str | None, str]:
    """The aii-web-tools extractor, verbatim in spirit: PDF via fitz, HTML via
    html2text. Returns (raw_text, status)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = _session.get(url, allow_redirects=True, timeout=timeout)
        if resp.status_code >= 400:
            return None, f"http-{resp.status_code}"
        ctype = (resp.headers.get("content-type") or "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            doc = fitz.open(stream=resp.content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text, "ok"
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(resp.text), "ok"
    except Exception as e:  # report, don't crash the audit
        return None, f"error:{type(e).__name__}"


def normalize(text: str) -> str:
    text = text.replace('\\"', '"').replace("\\'", "'")
    text = re.sub(r"\\([^\w\s])", r"\1", text)  # html2text escapes punctuation
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # md links → their text
    text = unicodedata.normalize("NFKC", text)
    text = (
        text.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("…", "...")
        .replace("­", "")
        .replace(" ", " ")
    )
    text = re.sub(r"[*_`#>|]", "", text)  # markdown presentation, not words
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return text.strip().lower()


def quote_found(quote: str, page_norm: str) -> bool:
    q = normalize(quote)
    if len(q) < MIN_LEN:
        return True  # too short to verify meaningfully; structural lint flags these
    # PDF line-break hyphenation: "multi-\ncause" → "multi- cause". Rejoin both
    # ways (compound split keeps the hyphen; soft-hyphenated word drops it).
    variants = (
        page_norm,
        re.sub(r"(\w)- (\w)", r"\1-\2", page_norm),
        re.sub(r"(\w)- (\w)", r"\1\2", page_norm),
    )
    if any(q in v for v in variants):
        return True
    segs = [s.strip() for s in re.split(r"\.\.\.", q) if len(s.strip()) >= MIN_LEN]
    if len(segs) > 1:  # elided quote: all segments present, in order
        for v in variants:
            pos, ok = 0, True
            for seg in segs:
                i = v.find(seg, pos)
                if i < 0:
                    ok = False
                    break
                pos = i + len(seg)
            if ok:
                return True
    return False


def collect(bundle: Path) -> list[dict]:
    items: list[dict] = []
    for md in sorted(bundle.glob("*.md")):
        body = md.read_text(encoding="utf-8", errors="replace")
        for m in QUOTE_LINK.finditer(body):
            items.append({"file": md.name, "quote": m.group(1), "url": m.group(2)})
        if md.name == "SOURCES.md":  # table format: url + quotes share a row
            for line in body.splitlines():
                if not re.match(r"\|\s*⚠?️?\s*S\d+\s*\|", line):
                    continue
                cells = [c.strip() for c in line.split("|")]
                urls = TABLE_URL.findall(line)
                if not urls or len(cells) < 5:
                    continue
                for q in TABLE_QUOTE.findall(cells[4] if len(cells) > 4 else ""):
                    items.append({"file": md.name, "quote": q, "url": urls[0]})
    seen, out = set(), []
    for it in items:  # de-dup pairs picked up by both patterns
        key = (normalize(it["quote"])[:120], it["url"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    items = collect(args.bundle)
    if not items:
        print("NO QUOTES FOUND — a handbook without quote anchors fails the format")
        return 1

    pages: dict[str, tuple[str | None, str]] = {}

    def get(url: str) -> tuple[str | None, str]:
        if url not in pages:
            raw, status = fetch_content(url, args.timeout)
            pages[url] = (normalize(raw) if raw else None, status)
        return pages[url]

    results = []
    for it in items:
        page, status = get(it["url"])
        m = re.search(r"arxiv\.org/pdf/([\w.]+?)(?:v\d+)?(?:\.pdf)?$", it["url"])
        if status != "ok" and m:  # arXiv PDF cite → same work's /abs/ page
            page, status = get(f"https://arxiv.org/abs/{m.group(1)}")
        if status == "ok":
            verdict = "OK" if quote_found(it["quote"], page or "") else "SOFT-MISS"
        else:
            verdict = f"FETCH-FAIL({status})"
        results.append({**it, "verdict": verdict})
        mark = "✓" if verdict == "OK" else "✗"
        print(f'{mark} [{verdict}] {it["file"]}: "{it["quote"][:70]}…" → {it["url"][:80]}')

    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"].split("(")[0]] = counts.get(r["verdict"].split("(")[0], 0) + 1
    print(f"\nSUMMARY: {counts} of {len(results)} quotes across {len(pages)} urls")
    print(
        "SOFT-MISS = fetched (harvest-identical extractor) but quote not located"
        " verbatim → fix the quote/URL or demote to candidate lane."
    )
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
    hard = sum(1 for r in results if r["verdict"] != "OK")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
