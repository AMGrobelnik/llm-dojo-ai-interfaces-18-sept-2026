<!-- hook: flow-byo-openrouter-key -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_APP_URL
# OpenHands needs a key of your own unless you are a superuser, and every backend shows its capacity

A MACHINE rule: the command runs `scripts/byo_key_flow.mjs` (Playwright,
resolved from the repo's frontend package via `rules-fe-root`). With no
`RULES_APP_URL` the command exits 0 — the engine idiom for live-app rules
skipping the commit path — so it bites only when a base URL is provided.

**Export `AMG_HOOKS_APP_URL`, not `RULES_APP_URL`.** `lib/amg_hooks/amg-hooks-env` assigns
`RULES_APP_URL="${AMG_HOOKS_APP_URL:-}"` unconditionally, so a `RULES_APP_URL` you
export yourself is overwritten with empty and this lane stays dormant while
looking opted-in. Measured 2026-09-14 through amg-hooks-env: with `RULES_APP_URL`
exported the hook saw `[]`; with `AMG_HOOKS_APP_URL` exported it saw the URL. Since
the consumer sets neither, the lane has never run at a commit — which is the
design, but was SILENT until 2026-09-14. It now prints
`skipped: AMG_HOOKS_APP_URL unset (opt-in lane, see README)` to stderr, so a lane
that did nothing cannot be read in the gate output as a lane that ran and
found nothing. `general/hooks/gate-can-fire` reaches the same verdict from the
other side and ships this command as recorded debt, a VACUOUS PASS; the gate
keeps its `[ -n … ] || { …; exit 0; }` shape precisely so that hook goes on
matching it.

It also needs `AII_DEMO_ADMIN_PASSWORD` and `OPENROUTER_API_KEY` in the
environment (`set -a; . .env; set +a` from the checkout), and a REGULAR
account on the target app in `RULES_FLOW_USER_EMAIL` /
`RULES_FLOW_USER_PASSWORD` — a non-superuser with a verified email. The
two bootstrapped accounts do not qualify: `staff@aii.local` is a
superuser by explicit instruction (``staff_bootstrap.py``: entitlement is
the point of it), and so of course is the admin. Provision one on the
app's Django shell (``create_user`` + a verified ``EmailAddress`` row) or
sign one up and verify it; the script names a superuser as an infra
error, never a FAIL, because a superuser being granted the built-in key
is the product working.

What the script asserts, end to end, as two people:

* **The demo admin (a superuser)** — `GET /api/config` grants the built-in
  key (`openrouter_system_key: true`); on Configure → Models the OpenHands
  option is enabled and its hover explains the backend, not a missing key;
  the switcher shows three capacity dots; `GET /api/config/backend-capacity`
  answers for all three backends with a known state and Free reads ok.
* **The regular account (a non-superuser)** — the policy denies the
  built-in key; OpenHands is greyed out and its hover
  says to add a key; a `PUT /api/config` that switches to OpenHands is
  refused with the same sentence. Then the account types the deployment's
  OpenRouter key into the API Keys tab as its own: the row reads "In use",
  OpenHands is enabled, and the switch now saves. Cleanup removes the key
  and puts the backend back, and asserts OpenHands is greyed again.

Any miss exits 1 with a JSON verdict and a screenshot beside the script;
setup failures (login, a missing secret, a superuser handed in as the
regular account) exit 2 as infra, not FAIL. The stored key and the backend
switch are undone in a `finally`, so the regular account is left exactly
as found.

Why: this is the one place a wrong answer costs real money in either
direction — a regular user reaching the built-in key spends the
deployment's OpenRouter credit, and a superuser wrongly greyed out cannot
run OpenHands at all — and the whole decision lives across three seams
(role policy in yaml, the stored-key service, two switchers) that unit
tests cover one at a time. The Playwright e2e suite checks only that the
switcher renders.

Fix when failing: `openhands_key_gap` in
`aii_server/dashboard/services/user_api_keys.py` is the one decision;
`openrouter.system_key` in `aii_config/roles/*.yaml` is the policy;
`backendChoices` / `openHandsBlockedReason` in
`aii_frontend/features/run-config/run-settings.ts` is what both switchers
render; `dashboard/services/backend_capacity.py` is the dot.

Delete-check: cannot delete — a product invariant across three seams, not
a code convention. The script IS the flow, carried by the rule instead of
the never-run e2e suite.
