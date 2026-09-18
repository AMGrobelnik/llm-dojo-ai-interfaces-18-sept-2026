"""Wayback Machine fallback for URLs the live web will not serve.

A cited page that has moved, died, or started refusing bots is not the same
thing as a citation that is wrong — but downstream they looked identical,
because a 403 error page is still a body and the quoted sentence simply is not
in it. The verifier then reported INVALID, which reads as "the author
misquoted their source" when the truth is "nobody could open the source".

The Wayback Machine usually still has the page as it stood when the citation
was written, which is the version the claim was actually made against.

Two details that matter and are easy to get wrong:

* The CDX query filters ``statuscode:200`` and sorts newest-first. Without the
  filter the newest capture is often itself an archived 404 or a soft-blocked
  page, and you would faithfully retrieve the error the live site is already
  giving you.
* The snapshot URL carries the ``id_`` modifier (``/web/<ts>id_/<url>``). That
  returns the ORIGINAL bytes. The default form injects a Wayback toolbar and
  rewrites every link in the document, which changes the text and would break
  exact-quote matching — the one job the caller has.

Coverage is real but partial: an arXiv page or an old blog post is usually
there, a site that opts out via robots.txt or a page nobody ever visited is
not. `snapshot_url` returning None is the normal case for such pages, not an
error, and the caller should fall through to its existing failure path.
"""

from __future__ import annotations

import json
import urllib.parse

CDX_ENDPOINT = "http://web.archive.org/cdx/search/cdx"

# CDX is genuinely slow — measured 19.5 s for an arxiv.org/abs page and 15 s
# for example.com, both of which ARE archived. A 15 s budget looked like a
# coverage gap during development (arXiv reported "not archived") when it was
# only the clock running out, so do not tighten this without re-measuring: a
# too-short timeout here is indistinguishable from the page being absent, and
# fails in the silent direction.
CDX_TIMEOUT = 30


def snapshot_url(url: str, *, session, timeout: int = CDX_TIMEOUT) -> str | None:
    """Return a raw-content Wayback URL for ``url``, or None if not archived.

    ``session`` is the caller's existing requests session, so the fallback
    inherits whatever retry and header configuration the caller already set up
    rather than establishing a second, differently-behaved HTTP client.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        resp = session.get(
            CDX_ENDPOINT,
            params={
                "url": url,
                "output": "json",
                "limit": 1,
                "filter": "statuscode:200",
                "sort": "reverse",
                "fl": "timestamp,original",
            },
            timeout=timeout,
        )
        if resp.status_code != 200 or not resp.text.strip():
            return None
        rows = json.loads(resp.text)
    except Exception:
        # An unreachable archive must never turn a fetch failure into a crash;
        # the caller's own error path is the correct outcome.
        return None

    # Row 0 is the header when the response is non-empty; an archived-nothing
    # answer is the literal `[]`, which leaves nothing after the header.
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    row = rows[1]
    if not isinstance(row, list) or len(row) < 2:
        return None
    timestamp, original = row[0], row[1]
    if not timestamp or not original:
        return None
    return f"https://web.archive.org/web/{timestamp}id_/{urllib.parse.unquote(original)}"
