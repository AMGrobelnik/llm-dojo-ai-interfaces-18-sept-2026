<!-- hook: async-inline-blocking -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# No coroutine in aii_server performs blocking filesystem/subprocess/ORM work inline — it goes through asyncio.to_thread or sync_to_async

Recurring defect class with three landed fixes found one-by-one: cc5e250de
(side-chat POST blocked the shared event loop), 1ff4811ca (RunPod start path,
commit body: 'same defect as the side-chat POST, found by carrying that audit
across'), plus the in-code hazard notes at runs_helpers.py:547-550 and 565-570
('is_dir stats the SHARED VOLUME (NFS)... an inline stat freezes every
concurrent poll'). A prototype AST scan during this survey found a LIVE fourth
instance: runpod_provision.py:530 — user_config_dir.is_dir() inline in async
def launch_orchestrator_pod, a stat against USERS_DATA_DIR (NFS on the
deployment). The existing rule-server-handler-async-offload group pins only
the already-fixed handlers by thread identity; nothing scans the whole tree
for the next one.

Mechanism (implemented 2026-08-26, `scripts/check_async_inline_blocking.py`):

    .venv/bin/python $RULE_DIR/scripts/check_async_inline_blocking.py

**The live fourth instance this body names is FIXED, so the rule arrives
green.** `runpod_provision.py:530` is now a comment explaining the hazard, and
:535 reads `await asyncio.to_thread(user_config_dir.is_dir)`. Re-measured
2026-08-26: 102 coroutines under `aii_server`, 0 inline blocking calls, and 5
nested blocking helpers of which all 5 are offloaded.

It checks two shapes, because the house fix creates the second one. Inline
blocking in the coroutine's own body is the original defect; a helper that was
written but is then CALLED DIRECTLY is the same defect wearing the fix's
clothes, so each blocking nested helper is checked against the names actually
handed to `to_thread`/`sync_to_async` in that coroutine.

**Walking the whole coroutine is wrong and reports 18 phantoms.** `ast.walk`
descends into nested `def` bodies, so every correctly-offloaded helper looks
like an inline violation — measured, a naive walk reports 18 hits across
`aii_server` and all 18 are inside helpers that are properly offloaded.
Scope-aware traversal that stops at any nested `def`, `async def` or `lambda`
reports 0. A happy accident helps for free: `to_thread(p.is_dir)` passes the
bound method WITHOUT calling it, so there is no `Call` node to match and the
fixed form is invisible to the check.

ORM work is deliberately out of scope — whether a queryset touches the
database where it stands depends on lazy evaluation, which is a judgement, not
something a machine can see.

Probed six ways: both defect shapes fire; a helper handed to `to_thread`, a
bound method passed uncalled, a `sync_to_async` offload and blocking inside a
plain sync `def` all correctly do not.

Note on the superseded line below: it names `scripts/async_inline_blocking.py`
while the implementation is `check_async_inline_blocking.py`, matching the
`check_*` convention every other mechanism in this tree uses. The `$RULE_DIR/`
prefix was removed from that historical path deliberately — `ready.py` treats
EVERY `$RULE_DIR/<path>` occurrence in a rule body as a claim that the file
exists, so a superseded proposal naming a filename that was never built keeps
the rule in BLOCKED forever, mechanism or no mechanism. Measured here: with the
prefix present the rule stayed BLOCKED with a working command in its
frontmatter.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-server)

Proposed command (implemented at approval):

    python scripts/async_inline_blocking.py aii_server  # AST: inside async def bodies (lambdas/nested defs excluded, awaited async calls excluded) flag Path stat/read/write/mkdir/glob, open(), subprocess.*, shutil.*, time.sleep, .objects. at coroutine level; per-line '# blocking-ok: <why>' opt-out

Delete-check: Not deletable: the single-ASGI-worker deploy model is deliberate (cheap pod,
documented in the offload rule's Why), so the hazard is structural. The
complementary sync_to_async-vs-to_thread SPLIT stays with the thread-identity
tests, which their docstring proves source scans cannot judge — this rule only
bans the inline case, which source CAN judge.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Three landed fixes found one-by-one prove recurrence; server-handler-
async-offload unit tests pin the fixed sites, this catches NEW inline-blocking
coroutines whole-tree. Complementary, not duplicate.
- KEEP: Three landed fixes found one-by-one prove the class recurs; a curated-
pattern AST scan (open/subprocess/ORM inside async def without to_thread) is
worth the moderate false-positive/allowlist cost given a single-ASGI-worker
deploy. Scope it to aii_server only and keep the pattern list small to control
FP churn.
- KEEP: Implementable as a lexical denylist (subprocess, Path read/write,
open, ORM .objects/.save, time.sleep) inside async def bodies not wrapped in
to_thread/sync_to_async — catches exactly the two landed-defect shapes.
Indirect blocking via helpers is invisible, but the direct-call form is the
recurrent class; not vacuous.
