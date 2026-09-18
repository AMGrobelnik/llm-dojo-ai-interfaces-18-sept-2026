<!-- hook: prod-security-floor-pinned -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# settings.py's non-DEBUG branch keeps the pinned transport/cookie security floor, and a non-DEBUG boot refuses allow-all credentialed CORS

settings.py's non-DEBUG branch keeps the pinned transport/cookie floor —
SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE, CSRF_COOKIE_SECURE/SAMESITE,
SECURE_CONTENT_TYPE_NOSNIFF, X_FRAME_OPTIONS=DENY, the HSTS trio,
SECURE_PROXY_SSL_HEADER — and a non-DEBUG boot refuses allow-all credentialed
CORS.

The whole floor lives in one unguarded block
(aii_server/config/settings.py:534-545, re-measured 2026-08-28) that any
refactor can thin silently — no test or check outside this rule names these
flags anywhere in the rules tree (grepped). Committed server.yaml is
dev-posture (debug: true line 13, cors.allow_all: true line 30) with the
comment 'Production MUST run debug=false' (line 10), while settings.py:161-169
honors allow_all with no DEBUG guard and sets CORS_ALLOW_CREDENTIALS=True
unconditionally. What actually creates the production posture is
scripts/runpod/run_server.sh, which forces debug=false (line 308) and
cors.allow_all=false (line 328) into the private overlay at pod boot — and
that boot patch is itself unpinned, so a refactor deleting either line fails
nothing, and a deployment that bypasses run_server.sh would ship a
credentialed allow-all origin policy with no error.
Adjacent-not-duplicate: pending rule-security-headers-parity asserts
next.config.ts EQUALS what Django declares (cross-stack equality — it passes
even if both sides drop a header); this pins that Django's non-DEBUG floor
EXISTS with the pinned values, including the cookie flags Next cannot set.
Same genre as the claimed rule-tsconfig-strictness-floor, different artifact.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: access-parity)

Proposed command (implemented at approval):

    python scripts/check_prod_security_floor.py  # ast-parse settings.py, locate the `if not DEBUG:` module-level branch, assert the pinned assignment set/values, and assert the not-DEBUG allow-all-CORS refusal guard is present

Proposed condition: `none — static AST parse of one file, sub-second`


## IMPLEMENTED 2026-08-26 — the floor half; the CORS half is the owner's

    .venv/bin/python $RULE_DIR/scripts/check_security_floor.py

Arrives green: all 11 settings present in the `if not DEBUG:` branch with their
pinned values.

**It pins EXISTENCE, which is the half equality cannot cover.**
`rule-security-headers-parity` asserts Next equals Django; that passes just as
happily when BOTH sides drop a header, and says nothing about the cookie flags,
which Next cannot set. Values are pinned too, not just names —
`SESSION_COOKIE_SECURE = False` would satisfy a name-only check while removing
the protection outright.

**A probe caught a real design error before this shipped.** Deleting the whole
`if not DEBUG:` branch made the first version report *cannot-run* — which reads
as "the check could not run" when it is in fact the exact failure the rule
exists to catch. A missing branch is now a FINDING that names all 11 settings
as unapplied.

## The CORS half is NOT implemented, and deliberately

The rule also asks that "a non-DEBUG boot refuses allow-all credentialed CORS".
That refusal does not exist, and the exposure is real:

| fact | measured |
|---|---|
| `CORS_ALLOW_CREDENTIALS` | `True`, unconditionally |
| `cors.allow_all` honoured | with no `DEBUG` guard |
| committed `server.yaml` | `debug: true`, `allow_all: true` |

So a private overlay that sets `debug: false` and leaves `allow_all: true`
ships a credentialed allow-all origin policy with nothing reporting it.

Implementing it means adding a boot-time refusal to production settings — a
change that decides whether a deployment starts at all, on evidence that lives
in gitignored overlays this check cannot read. That is the owner's call, not a
mechanical one, and it is stated here rather than executed.

Probed six ways: a dropped flag, a weakened boolean, a relaxed
`X_FRAME_OPTIONS`, a shortened HSTS, and a deleted branch all fire; the real
settings do not.

Delete-check: Django's own deploy checklist now runs in the consumer's unit
suite — `tests/unit/server-settings/test_django_deploy_checklist.py` boots
the production settings under `override_settings` and runs
`checks.run_checks(tags=[security], include_deployment_checks=True)`, with
`security.W008` (SSL redirect: TLS ends at the proxy) the one accepted
warning. That covers the framework-maintained list (W012/W016/W004...)
without a debug-off override, since `override_settings` supplies DEBUG
in-process. This AST pin stays as the cheap commit-time floor for the
hand-chosen block itself; delete it once the checklist test has held for a
quarter and the block's own values are what the checklist asserts.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The whole non-DEBUG floor lives in one unguarded block no test names,
and the committed yaml is dev-posture, so a silent thinning ships. Keep, but
implement per its own delete-check as manage.py check --deploy under a prod-
shaped env plus the CORS assertion — framework-maintained checklist over a
hand list. Complementary to pending rule-security-headers-parity (FE/BE
equality, not the …
- KEEP: The whole transport/cookie floor lives in one unguarded settings block
with zero tests naming any flag; a source pin is a cheap grep now — with the
noted follow-up that folding in Django's own check --deploy is the eventual
framework-maintained form.
- KEEP: Keep, but mechanize via the framework: run manage.py check --deploy
under a prod-shaped settings import (its delete-check already names this) plus
one custom assert for the credentialed-CORS refusal, rather than hand-pinning
flag literals that drift. Distinct from pending rule-security-headers-parity
(cross-stack value parity, not the floor itself).

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Line refs re-measured and all exact: aii_server/config/settings.py:526 `# ----
Production security ----`, :527 `if not DEBUG:`, :528-538 the eleven flags.
settings.py:154 `if _cors_cfg.get("allow_all", False):` / :155
`CORS_ALLOW_ALL_ORIGINS = True` / :162 `CORS_ALLOW_CREDENTIALS = True` (no
DEBUG guard). aii_config/server/server.yaml:10 contains 'Production MUST run
debug=false', :13 `debug: true`.

Corrected statement of fact:
The prod contract is NOT prose-only, and a private-overlay mistake does not
ship a credentialed allow-all production origin policy:
scripts/runpod/run_server.sh forcibly writes server["debug"]=False (line 308)
and cors["allow_all"]=False (line 328) into server.private.yaml at pod boot,
before the server starts at line 447, overriding whatever the overlay carried.
server.yaml's comments at lines 11 and 28-29 name that script as the enforcer.
What IS true and worth pinning: (a) settings.py:527-538's non-DEBUG floor and
settings.py:154-162's unconditional CORS_ALLOW_CREDENTIALS=True beside a
DEBUG-agnostic allow_all are named by no active rule or test anywhere in the
tree; (b) the run_server.sh boot patch that actually creates the production
posture is likewise unpinned — a refactor deleting either line 308 or line 328
fails nothing. The rule's real subject is that pair of unguarded blocks plus
the boot patch, not an exposed live deployment. The allow-all-credentialed
risk applies only to a deployment that bypasses run_server.sh.
