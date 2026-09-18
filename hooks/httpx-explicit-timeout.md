<!-- hook: httpx-explicit-timeout -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every httpx client construction and module-level call carries an explicit timeout kwarg

AST scan across the six package trees: 40 of 41
httpx.(Client|AsyncClient|get|post|put|delete|request|stream) sites pass
timeout=; the single stray is
aii_lib/src/aii_lib/abilities/ability_server/ability_client.py:409
`httpx.AsyncClient()`. The convention is already the house norm down to named
constants (HTTP_TIMEOUT_S in claude_oauth/_accounts_health/_config.py), and
the user-level standing order is 'assume any call can hang'. Complements rule-
httpx-only (which pins the client library, not its timeout discipline); no
ruff rule covers httpx timeouts (S113 is requests-only).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: cross-cutting)

Mechanism (implemented 2026-08-26, `scripts/check_httpx_timeout.py`):

    .venv/bin/python $RULE_DIR/scripts/check_httpx_timeout.py

**The single stray was real but was NOT a live hang, and the distinction is
worth keeping.** `ability_client.py` built `httpx.AsyncClient()` bare, but the
one `post` inside that block passed `timeout=http_timeout`, and httpx lets a
per-request timeout override the client's — so nothing could hang there. What
the missing default created was a trap for the NEXT request added to that
block, which would silently inherit httpx's 5 s, far below the deadline the
call forwards. It was given the same explicit value, so the rule now arrives
green at 40 of 40 sites. (Its cited line 409 is 411 today.)

So this asserts EXPLICITNESS, not reachability: a timeout that is stated
cannot be silently inherited from a library default nobody in this tree chose.
That is deliberately stricter than "cannot hang", because proving reachability
needs dataflow analysis and this rule exists to avoid needing it.

Instance calls are deliberately out of scope — `client.post(…)` inherits the
client's timeout, so requiring one there would flag correct code and push
authors into repeating a value that already has a single source. Only
`httpx.<something>(…)` is checked.

Probed seven ways: a bare `AsyncClient()` and a bare module-level `httpx.get`
fire; a constructor with `timeout=`, a module call with `timeout=`, an
instance call, and a bare call under `/tests/` do not — and the floor bites on
a tree with no httpx sites at all, so an empty parse cannot read as clean.

Superseded proposal:

    python3 $RULE_DIR/scripts/check_httpx_timeout.py  # ast.walk over the six package trees flagging httpx constructor/verb calls whose keywords lack 'timeout'; verified today: exits naming exactly ability_client.py:409

Proposed condition: `git diff --cached -U0 -- '*.py' | grep -q 'httpx\.'`

Delete-check: The alternative collapse — one shared client factory with a default timeout,
deleting 40 per-site kwargs — is a 40-site refactor for zero behavior change
and hides the per-call budget the sites deliberately tune. Pin the already-
uniform explicit idiom; the one stray is a one-line fix at adoption.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: 40/41 explicit with one stray, and the inventory's gaps list names the
missing timeout convention. Fix the stray, pin the house norm; the factory-
refactor alternative is 40 sites of churn for zero behavior change.
- KEEP: Fills the inventory's named timeout-convention gap; 40/41 already
comply so adoption is one site. Per-site kwarg check is the right instrument
(the factory refactor is 40 sites for zero behavior change). Cheap AST scan,
low FP.
- KEEP: AST over httpx constructor/module-call sites requiring timeout kwarg —
40/41 already comply, one stray to fix. Deterministic, loud; its delete-check
rightly rejects the 40-site factory refactor.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
My own ast.walk over the six package trees (aii_lib, aii_server, aii_pipeline,
aii_runpod, aii_launcher, claude_cred_manager), flagging httpx.(Client|AsyncCl
ient|get|post|put|delete|patch|head|options|request|stream) calls without a
`timeout` keyword, prints: 'total httpx call sites: 40 / missing timeout: 1 /
aii_lib/src/aii_lib/abilities/ability_server/ability_client.py:411
httpx.AsyncClient(kwargs=[])'. So the total is 40, not 41, and the line is
411, not 409. Reading 398-420 of that file show

Corrected statement of fact:
There is no timeout-less httpx call in the tree. The single flagged site is a
constructor whose request carries an explicit deadline-derived timeout on the
very next line, and httpx's own default is a 5 s Timeout rather than 'no
timeout', so the 'assume any call can hang' framing does not transfer from
requests to httpx. A rule keyed on the constructor would flag correct code
and, as written, would also flag the house's own documented usage example in
aii_lib/src/aii_lib/utils/internal_auth.py:19 (module docstring:
`httpx.get(url, headers=internal_headers())`).
