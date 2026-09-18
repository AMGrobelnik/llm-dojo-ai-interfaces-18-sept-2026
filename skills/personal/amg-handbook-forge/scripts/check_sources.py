#!/usr/bin/env python3
"""Structural source audit for a generated handbook bundle (no LLM judgment).

Mechanical checks the credibility scrutiny pass builds on:
  1. Every [Sn] cited anywhere resolves to a SOURCES.md row; every row is used.
  2. Every source row is complete: tier (A-E, or L=Landscape), non-empty reliable-for scope,
     >=1 verbatim quote.
  3. Shared-origin accounting: sources on the same registrable domain are
     grouped and flagged — corroboration = one vote per origin.
  4. Preprint/self-published markers (arxiv, ssrn, medium, substack, personal
     blogs) flagged: peer-review / self-report status must be stated in the row.
  5. Candidate-lane hygiene: every unverified marker outside the Candidate
     lane section of SKILL.md is an error.

The judgment half (credibility verdicts) is the agent's scrutiny pass per
credibility.md — this script only proves the artifacts of that pass exist.

Usage:  python3 check_sources.py <bundle-dir>
Exit:   0 clean · 1 any ERROR (warnings don't fail the audit)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SREF = re.compile(r"\[S(\d+)\]")
MIN_PROSE_QUOTE = 25  # below this, a quoted string is usually scare-quotes/terminology


def _norm(s: str) -> str:
    """Conservative normalization for prose-quote matching (never changes words)."""
    s = (
        s.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("—", "-")
        .replace("–", "-")
        .replace("…", "...")
    )
    s = re.sub(r"[*_`>]", "", s)  # markdown emphasis/blockquote is presentation, not words
    return re.sub(r"\s+", " ", s).strip().lower()


SROW = re.compile(r"^\|\s*⚠?️?\s*S(\d+)\s*\|", re.M)
URL = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}/[^\s|)\]>]*[^\s|)\]>.,]")
QUOTE = re.compile(r"[\"“].{15,}?[\"”]", re.S)
TIER = re.compile(r"\b([A-EL])\b")  # A–E + L (Landscape syntheses), per SKILL.md §Sources
PREPRINTY = ("arxiv.org", "ssrn.com", "medium.com", "substack.com", "openreview.net")
MULTI_TENANT = (
    "github.com",
    "github.io",
    "githubusercontent.com",  # raw./gist. — per-repo, not one shared origin
    "medium.com",
    "substack.com",
    "wordpress.com",
)
# hosts where co-location says nothing about shared authorship — never one-vote them
REPOSITORIES = (
    "arxiv.org",
    "openreview.net",
    "ssrn.com",
    "doi.org",
    "proceedings.neurips.cc",
    "dl.acm.org",
    "huggingface.co",
)


def origin(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    m = re.match(r"https?://web\.archive\.org/web/[^/]+/(.+)", url)
    if m:  # Wayback snapshot: the real origin is the embedded URL
        return origin(m.group(1))
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if any(host == r or host.endswith("." + r) for r in REPOSITORIES):
        return url.rstrip("/")  # each work is its own origin
    if any(host == m or host.endswith("." + m) for m in MULTI_TENANT):
        path = urlparse(url).path.strip("/").split("/")
        return f"{host}/{path[0]}" if path and path[0] else host  # per-account origin
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    args = ap.parse_args()
    errors: list[str] = []
    warns: list[str] = []

    sources_md = args.bundle / "SOURCES.md"
    if not sources_md.exists():
        print("ERROR: SOURCES.md missing")
        return 1
    src_body = sources_md.read_text(encoding="utf-8", errors="replace")

    # --- parse source rows ---
    rows: dict[str, dict] = {}
    for line in src_body.splitlines():
        m = SROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.split("|")]
        sid = f"S{m.group(1)}"
        urls = URL.findall(line)
        tier_cell = cells[3] if len(cells) > 3 else ""
        quote_cell = cells[4] if len(cells) > 4 else ""
        rows[sid] = {
            "url": urls[0] if urls else None,
            "tier": bool(TIER.search(tier_cell)),
            "candidate": "⚠" in line,
            "reliable_for": len(re.sub(r"[A-EL·\s—-]+", "", tier_cell)) > 3,
            "quote": bool(QUOTE.search(quote_cell)),
        }
    if not rows:
        print("ERROR: no source rows parsed from SOURCES.md")
        return 1

    # --- collect [Sn] references across the bundle ---
    used: set[str] = set()
    for md in sorted(args.bundle.glob("*.md")):
        body = md.read_text(encoding="utf-8", errors="replace")
        refs = {f"S{n}" for n in SREF.findall(body)}
        if md.name != "SOURCES.md":
            used |= refs
        for sid in refs:
            if sid not in rows:
                errors.append(f"{md.name}: [{sid}] cited but not defined in SOURCES.md")
        if md.name == "SKILL.md":  # candidate-lane hygiene
            lane_at = body.find("Candidate lane")
            for mm in re.finditer(r"⚠️", body):
                if lane_at < 0 or mm.start() < lane_at:
                    ln = body[: mm.start()].count("\n") + 1
                    if "=candidate" in body[max(0, mm.start() - 60) : mm.start() + 60]:
                        continue  # the banner legend
                    errors.append(f"SKILL.md:{ln}: ⚠️ marker outside the Candidate lane")

    # --- orphan prose quotes -------------------------------------------------
    # verify_quotes.py only fetches quotes it finds in SOURCES.md rows and in
    # ["quote"](url) links, so a BARE "quoted string" in SKILL.md/volatile.md prose
    # is never checked against any source. Require every such quote to appear
    # verbatim in SOURCES.md, so it inherits that row's fetch-verification.
    # Scoped to quoted strings on a line that also carries an [Sn] — i.e. quotes
    # presented as cited evidence — which excludes scare-quotes and terminology.
    src_norm = _norm(src_body)
    for md in sorted(args.bundle.glob("*.md")):
        if md.name == "SOURCES.md":
            continue
        body = md.read_text(encoding="utf-8", errors="replace")
        if body.startswith("---"):  # drop YAML frontmatter; descriptions are not claims
            body = body.split("\n---", 1)[-1]
        # Collapse to one line FIRST: quotes routinely wrap, and per-line splitting
        # would pair the quote characters wrongly and invent phantom spans.
        flat = re.sub(r"\s+", " ", body)
        parts = re.split(r'["“”]', flat)
        pos = 0
        for i, seg in enumerate(parts):
            pos += len(seg) + 1
            if i % 2 == 0:  # even segments are outside quotes
                continue
            if len(seg.strip()) < MIN_PROSE_QUOTE:
                continue
            # only judge quotes presented as cited evidence: an [Sn] must follow closely
            if not SREF.search(flat[pos : pos + 120]):
                continue
            if _norm(seg) not in src_norm:
                warns.append(
                    f"{md.name}: prose quote not in SOURCES.md — verify it is a paraphrase/"
                    f'label, not an unchecked source quote: "{seg[:70]}…"'
                )

    # --- per-row completeness ---
    for sid, r in sorted(rows.items(), key=lambda kv: int(kv[0][1:])):
        if not r["url"]:
            errors.append(f"{sid}: no URL")
        if not r["tier"] and not r.get("candidate"):
            errors.append(f"{sid}: no tier letter (A–E or L) and not ⚠️-candidate")
        if not r["reliable_for"]:
            errors.append(f"{sid}: reliable-for scope empty — scrutiny pass incomplete")
        if not r["quote"]:
            errors.append(f"{sid}: no verbatim grounding quote")
        if sid not in used:
            warns.append(f"{sid}: defined but never cited outside SOURCES.md")
        if r["url"] and any(p in r["url"] for p in PREPRINTY):
            if not re.search(
                rf"{sid}.*?(preprint|peer.?review|proceedings|journal|"
                rf"self.?report|vendor|blog)",
                src_body,
                re.I | re.S,
            ):
                warns.append(f"{sid}: preprint/self-published host — state review status")

    # --- shared-origin accounting ---
    by_origin: dict[str, list[str]] = {}
    for sid, r in rows.items():
        if r["url"]:
            by_origin.setdefault(origin(r["url"]), []).append(sid)
    for org, sids in sorted(by_origin.items()):
        if len(sids) > 1:
            note = (
                "one-vote"
                if re.search(r"one.?vote|shared.?origin", src_body, re.I)
                else "NO one-vote note"
            )
            (warns if note == "one-vote" else errors).append(
                f"shared origin {org}: {sorted(sids)} — corroboration = one vote ({note})"
            )

    for e in errors:
        print(f"ERROR {e}")
    for w in warns:
        print(f"warn  {w}")
    print(
        f"\nSUMMARY: {len(rows)} sources · {len(used)} cited · "
        f"{len(errors)} errors · {len(warns)} warnings"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
