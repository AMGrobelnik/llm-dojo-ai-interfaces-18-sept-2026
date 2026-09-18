<!-- hook: route-decl-complete -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every Ninja route declares an explicit operation_id and response schema; the streaming download is the sole pinned exception

Measured by AST audit this survey: 39/39 routes declare operation_id, 38/39
declare response= — the sole omission is files/_run.py:482 download_file,
which streams bytes and legitimately has no schema. Ninja auto-derives
operation ids from function names when omitted, so a missing declaration
churns the generated Hey-API SDK method names the frontend is required to use
(aii/frontend rule-api-via-sdk) and shows up as generated-artifact drift —
recurring class 5 (0ba51b5fb, 84fc6199b, 92958849e all regenerate the client
after schema-affecting edits). The pattern is at 100%/97% by hand today; one
AST check keeps it there.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: python-server)

Mechanism (implemented 2026-08-26, `scripts/route_decorators_complete.py`):

    .venv/bin/python $RULE_DIR/scripts/route_decorators_complete.py

Arrives green, and the body's audit re-verified exactly: **39 routes, 39
declare `operation_id`, 38 declare `response=`**, the sole omission being
`download_file`. Its line moved from 482 to 523 when that module gained a WHY
docstring, which is why the allowlist keys on the HANDLER NAME rather than a
line number.

The exception is pinned in both directions: a route missing a declaration and
not listed fails, and a listed route that starts declaring one also fails, so
the exemption cannot outlive the streaming handler that earned it.

AST rather than grep, because the decorator is a call whose keywords wrap
across lines and both `@router.get` and `@api.get` forms appear — a
line-oriented search either misses the wrapped keywords or matches the word
`response` in a docstring. Probed six ways, including a decorator with its
keywords spread over four lines: a missing `operation_id`, a missing unpinned
`response`, and a pinned route that starts declaring one all fire; a complete
route, a pinned streaming route and the wrapped form do not.

Superseded proposal:

    python $RULE_DIR/scripts/route_decorators_complete.py  # AST: every @router.<verb>/@api.<verb> decorator in aii_server carries operation_id= and response=, allowlist {download_file}

Delete-check: The dimension (Ninja permitting omission) cannot be deleted without forking
Ninja; declaring explicitly IS the deletion of the auto-naming variation. A
Router wrapper requiring both kwargs would make it structural — same promotion
path as rule-public-route-run-gate, and the two could share one wrapper.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: 39/39 operation_id, 38/39 response= with one legitimate exception —
cheap AST pin that stops auto-derived SDK names churning the generated client
on a rename; complements hey-api-client-regen-clean, which detects but does
not prevent the churn.
- KEEP: 39/39 and 38/39 today; a missing operation_id churns the generated SDK
on any function rename. Cheap AST scan with one pinned exception. Low value
alone but near-zero cost and it front-stops churn the regen rule would only
detect after the fact.
- KEEP: AST over ninja route decorators asserting operation_id= and response=
kwargs with one pinned exception. Deterministic, loud, zero false positives on
today's 39/39 measured surface.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds, exactly.**

39 routes, all declaring `operation_id`, exactly one lacking `response=`
— and that one is `files/_run.py` `download_file`, which this body already
names as the sole pinned exception. A file download returns bytes, not a
schema, so the exception is principled rather than an oversight.

Detection note: the 39 is **38 on `router` + 1 on `api`**. An AST scan
that accepts only `router.get/post/...` as a decorator base reports 38 and
looks like drift. Any implementation must accept both bases.
