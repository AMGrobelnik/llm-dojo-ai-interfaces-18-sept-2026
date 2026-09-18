<!-- hook: commit-scopes -->

| stage | scope | budget | status |
|---|---|---|---|
| commit-msg | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MSG_FILE, RULE_DIR
# Commit scope comes from the closed vocabulary in this rule's check.sh

Measured over 6 months: 466 distinct scopes, 259 used exactly once, with
synonym clusters (`fe`/`frontend`/`ui`, `figs`/`fig`/`data-fig`, `run`/`runs`,
`test`/`tests`) — which breaks the one thing scopes are for: filtering
history. The commit-msg hook enforces the TYPE list but left the scope open;
this rule closes it.

The vocabulary lives in `check.sh` beside this file (49 entries, measured
2026-08-28; the count drifts as scopes are added). It deliberately starts
GENEROUS (top measured scopes, synonyms still included) so it never blocks
mid-flow work; the tightening — collapsing `fe|frontend|ui → fe`,
`figs|fig → data-fig|concept-fig`, `run|runs → run`, `test|tests → tests` —
is an owner decision, made by editing one list.

Fix when blocked: pick the nearest listed scope, or add the genuinely new
scope to `check.sh` in the same commit (the diff then shows the vocabulary
grew, which is the reviewable event).

Delete-check: cannot delete — subjects need some grouping axis; an open
vocabulary is the alternative and it measurably failed (466 scopes).
