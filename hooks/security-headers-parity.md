<!-- hook: security-headers-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The page security headers next.config.ts sets equal the values Django's settings.py declares

next.config.ts:145-174 explicitly states 'the values mirror Django's exactly,
so the two origins now agree' — X-Frame-Options DENY, nosniff, Referrer-Policy
same-origin, HSTS max-age=31536000 includeSubDomains preload vs
aii_server/config/settings.py:533-537 (SECURE_CONTENT_TYPE_NOSNIFF,
X_FRAME_OPTIONS='DENY', SECURE_HSTS_SECONDS=31536000, INCLUDE_SUBDOMAINS,
PRELOAD). That is a twin implementation in two languages with nothing
connecting them — recurring defect class #1 (584f91167, 69279ba42) — and the
incident that motivated the block was exactly this asymmetry: /api/health
carried HSTS+DENY+nosniff while /runs carried only x-powered-by. The rule-
server-frontend-parity test group covers CSRF names, URL prefixes and the
allauth path, but zero header tests (grepped: no X-Frame/HSTS/nosniff match in
its files).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: frontend-config)

Mechanism (implemented 2026-08-26, `scripts/check_header_parity.py`):

    .venv/bin/python $RULE_DIR/scripts/check_header_parity.py

Arrives green: 4 headers compared, all matching.

**One of them matches only because of a FRAMEWORK DEFAULT, and comparing
declarations alone would miss it.** `SECURE_REFERRER_POLICY` is never set in
`settings.py`; Django's own default is `same-origin`, which is exactly what
Next declares. The two agree today through a value nobody in this repo wrote.
A checker reading only the settings file would find no counterpart and either
skip the header — checking nothing — or report a break that is not one. This
resolves Django's EFFECTIVE value: the declaration when there is one,
otherwise `django.conf.global_settings`, imported directly since it is a plain
module of constants needing no app registry. A Django upgrade changing that
default now surfaces here instead of silently splitting the two origins.

HSTS is three Django settings and one wire header, so the comparison assembles
Django's side into `max-age=N; includeSubDomains; preload` rather than asking
the Next config to be expressed as three values. The settings also live inside
a production-only `if`, so the parse walks the whole tree — a module-level-only
scan finds none of them.

Probed five ways: a tightened `X-Frame-Options`, a shortened HSTS, and a header
Next drops all fire; agreement passes, and so does a config formatted without
the space after `source:` — that last one found real brittleness, since the
first version matched the literal `source: "` and reported the blanket route as
missing.

Superseded proposal:

    python3 $RULE_DIR/scripts/check_header_parity.py  # regex-extracts the four header values from next.config.ts headers() and the SECURE_*/X_FRAME_OPTIONS constants from settings.py; fails on any mismatch

Delete-check: The duplication cannot be deleted: the SPA is served by 'next start' on its
own port, so Django cannot stamp headers on page responses — two writers are
structural. When two writers must state one policy, a parity gate is the
standard fix (same reasoning as the existing cost-wire-parity and dashboard-
copy-parity groups).

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Two writers are structural (Next serves pages, Django serves the API)
and the mirror is declared in a comment only; a cmd parity check is the
cheapest honest closure for header drift between origins.
- KEEP: Two writers are structurally forced (next start serves pages; Django
can't stamp them) and the values are security headers whose silent divergence
weakens one origin. Small literal-parity check, condition-gated on the two
files.
- KEEP: Demote both sides to the house parity-fixture pattern: a shared
expected-headers fixture read by a Python test (Django settings→headers) and a
vitest (next.config.ts headers()). Direct two-language extraction would be
brittle; the fixture form is deterministic and loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
Django side is exact: settings.py:527 `if not DEBUG:`, 533
SECURE_CONTENT_TYPE_NOSNIFF=True, 534 X_FRAME_OPTIONS="DENY", 535
SECURE_HSTS_SECONDS=31536000, 536 SECURE_HSTS_INCLUDE_SUBDOMAINS=True, 537
SECURE_HSTS_PRELOAD=True — the cited 533-537 range is correct. Next side:
`grep -n` gives headers() at 139, X-Frame-Options DENY at 168, nosniff at 169,
Referrer-Policy same-origin at 170, Strict-Transport-Security at 172-173 with
`max-age=31536000; includeSubDomains; preload`. The quoted sentence "

Corrected statement of fact:
The four header values do agree today, so there is nothing to fix — this is a
preventive pin, not a live defect. Two corrections for whoever writes it: (1)
the block is next.config.ts:145-176, not 145-174; (2) one of the four values,
Referrer-Policy, has no counterpart in settings.py at all, so a test that
reads the settings SOURCE will find nothing to compare — it must read the
resolved `django.conf.settings.SECURE_REFERRER_POLICY` (Django 6.1 default
'same-origin'). Also worth noting the two sides are not literally symmetric:
Django's block is gated on `if not DEBUG` while the Next headers are
unconditional.
