<!-- hook: csrf-gate-once -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Browser CSRF enforcement has exactly one implementation — every auth gate calls the shared helper, never ninja's check_csrf directly

The identical origin-sniff + check_csrf block is hand-copied three times in
aii_server/dashboard/api/__init__.py: aii_auth (lines 40-47), _require_auth
(lines 127-138), and _require_run_access (lines 493-499). This is the exact
twin-drift class the same file already documents killing once:
run_owner_username's docstring (lines 231-238) records three drifted owner-
resolver copies producing a real staff-resolution defect before being
collapsed. A fourth CSRF copy in a new gate, or an edit landing in only two of
three, silently weakens one entry path.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-server)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/csrf_single_site.py  # AST over aii_server/: every call to check_csrf must sit inside dashboard/api/__init__.py::_browser_csrf_fails; any call elsewhere fails

The helper is `_browser_csrf_fails`, not the `_browser_csrf_error` this
proposal guessed at. It returns a BOOL, because what the three gates share is
the QUESTION and not the answer — `aii_auth` raises `HttpError` while the
other two build a Ninja response, so a helper returning an error object would
have forced one caller's failure shape onto the others.

ADOPTION (2026-08-25): the three hand-copies are collapsed. Equivalence was
proven rather than argued — both original spellings (the inline nesting, and
the variant reading a precomputed `safe_method`) and the helper were
transcribed as plain functions and compared across all 144 combinations of
method, origin, referer and `check_csrf` result, with zero mismatches. Each
caller's failure response is unchanged byte for byte; only indentation moved.

Verified against history rather than a synthetic fixture: run over the tree
before the consolidation, the gate exits 1 and names all three sites —
`aii_auth`, `_require_auth`, `_require_run_access` — at the lines this
proposal recorded. On today's tree it exits 0.

It counts CALLS via AST, never text hits: this module discusses
`check_csrf` in prose, and a grep would report the explanation as a second
implementation.

Delete-check: Deletion IS the proposal: collapse the three copies into one
_browser_csrf_error(request) helper called by
aii_auth/_require_auth/_require_run_access, then the rule enforces the
collapsed end-state (exactly one check_csrf call site). CSRF itself cannot be
deleted — Ninja marks its views csrf_exempt, so the in-gate check is the only
enforcement.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Delete-first done right: collapse three hand-copied origin-sniff
blocks into one helper, then the cmd check pins the end-state. Same twin-drift
class the file already documents killing once; access-control parity, cheap
grep.
- KEEP: Three hand-copied CSRF blocks in one file, in the exact twin-drift
class this repo has already paid for once. Collapse-then-grep is near-zero
cost and the post-collapse check is a single-file grep.
- KEEP: Cleanly mechanizable: after collapsing to one helper, grep for direct
check_csrf( calls outside it in dashboard/api. Ban-greps fail loudly on any
new copy; no vacuity trap.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
`grep -n "check_csrf" aii_server/dashboard/api/__init__.py` returns hits only
at 44,46 / 120,130,132 / 498,500 — three code copies, so the count holds. Line
cites: aii_auth 40-47 EXACT; _require_auth 127-138 EXACT; the third is at
495-501, not 493-499 (line 493 is `if user.is_authenticated:`, 499 is blank).
The owner-resolver docstring precedent is at 232-238, not 231-238 (231 is
blank) — text confirmed: 'This used to be three separate functions … two of
them ended in a bare return request.user.

Corrected statement of fact:
Three CSRF blocks exist, at 40-47, 127-138 and 495-501 (not 493-499). They
share an identical origin-sniff but differ in error mechanism (raise vs
return). The repetition is not an unnoticed copy-paste: it is declared
deliberate defence-in-depth by comments at :30-33 and :494 and by the pinning
test's own docstring, and two of the three layers already have mutation-
resistant tests. No drift is present.
