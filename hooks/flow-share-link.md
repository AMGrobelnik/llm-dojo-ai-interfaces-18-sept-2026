<!-- hook: flow-share-link -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-fe-root, RULES_APP_URL
# A share link opens the run read-only, logged out

A MACHINE rule: the command runs `scripts/share_flow.mjs` (Playwright,
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

What the script asserts, end to end: a logged-in context signs in as the
demo admin, opens a completed run, shares it, and reads the `/r/` URL from
the share popover; a FRESH logged-out context then opens that URL. PASS
requires all three: no login wall (no /login redirect, no password field),
run content rendered on an OK response, and ZERO owner-only controls
(stop/delete/rename/resume buttons). Any miss exits 1 with a JSON verdict
and a screenshot beside the script; setup failures exit 2 as infra, not
FAIL.

Why: sharing is the product's only outward loop, and a broken share link
fails silently — the owner never clicks their own share links, and the
recipient who hits the wall does not report it. The repo's 39 never-executed
Playwright specs are the cautionary tale this rule exists to end: a flow
nobody runs is green by definition.

Fix when failing: `aii_frontend/lib/share-access.ts` and the
`aii_optional_auth` routes are the two halves of the contract (note the
audit found 3 share-readable routes still on `auth=None` dropping identity —
that asymmetry is the likely culprit).

Delete-check: cannot delete — this is a product invariant, not a code
convention. The later-mechanization this line once promised has happened:
`share_flow.mjs` IS the Playwright spec, carried by the rule itself instead
of the never-run e2e suite.
