<!-- hook: in-process-durations-monotonic -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: condition was a content regex over the diff: the checker must return 0 fast when absent runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# An elapsed time or deadline that never leaves the process is measured with time.monotonic(); time.time() is reserved for stamps that cross a process, disk or wire boundary

The house doctrine is already written down, in the free_router:
`aii_lib/src/aii_lib/free_router/__init__.py:85` and `router.py:93` declare
`clock: Callable[[], float] = time.monotonic`; `reliability.py:143-145` states
the exception verbatim — "WALL clock, not the router's injected ``clock``:
that defaults to ``time.monotonic``, whose zero differs per process, so a
timestamp written by one pipeline process would decay nonsensically in
another"; and `_transport.py:85-86` converts an external absolute HTTP-date
into a DELTA "so it transfers safely onto the router's monotonic clock". RAN a
prototype AST checker (walks the six package trees; flags a function where a
name is bound from a `time.time()` expression and later compared with, or
subtracted from, another `time.time()` call in the SAME function — i.e. both
operands are wall-clock and neither leaves the process): output `paired wall-
clock duration sites: 6` — repl_driver.py:329 (start(), deadline bound :326),
:491 (run(), deadline :547), :562 (run(), `elapsed = time.time() -
turn_start`, turn_start :482), :601 (capture_cost_dialog(), deadline :597),
claude_oauth/autologin/_autologin/_verify.py:164 (deadline :162),
claude_oauth/usage.py:381 (deadline :380). I read 310-340, 470-620 of
repl_driver.py, 150-175 of _verify.py and 368-392 of usage.py: NO comment
declares wall clock deliberate at any of the six; they are stall windows and
poll deadlines, all strictly in-process. Zero false positives — the checker
does not flag the legitimately-wall-clock sites: `_helpers.py:249
deadline_epoch` (crosses into a hook subprocess via
`AII_TURN_DEADLINE_EPOCH`), `_backoff.py:87 backoff_until` and
`refresher.py`/`relogin.py`/`cred usage.py` (persisted to JSON, must survive
restart), `spawn.py:46` (compared against filesystem mtime),
`event_step.py:171`/`journal_writer.py:278` (wire `*_epoch_ms`). RAN the
inverse check too (does any monotonic value reach a serialization sink?): 1
hit, `sdk_openhands_agent/_agent/_turn.py:356`, and it passes a DIFFERENCE
(`runtime_seconds=time.monotonic() - started`), which is correct — so the
wall-clock direction is the only live gap. Adoption today: `git grep -c
'time.monotonic()'` shows 32 sites across aii_lib/aii_pipeline/aii_runpod
already on the right side, notably every deadline loop in aii_runpod
(orchestrator_client.py:288, _pod_launcher/_wait.py:102, ssh.py:114).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: time-and-clocks)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_wall_clock_durations.py   # ast.walk over package source, derived as any tracked *.py under a src/ tree; flags a function binding a name from time.time() that is later compared/subtracted against another time.time() call in the same function.

Condition: `git diff --cached -U0 -- '*.py' | grep -q 'time\.time()'`

ADOPTION (2026-08-25): the six sites this rule was written against are FIXED,
so the gate is green on the tree it gates rather than red on arrival. Four
poll deadlines in `repl_driver.py` (the bypass-prompt watcher, the turn
stall window with its `turn_start`/`hard_cold_deadline`/`elapsed` family, and
the cost-dialog capture), one in `_autologin/_verify.py`, one in `usage.py` —
each a local deadline compared only against sibling `time.time()` calls, none
serialized. `_verify.py`'s `expiresAt` was deliberately left alone: it is
written to JSON as an absolute epoch, which is the documented exception. The
491 tests in the three groups covering those modules pass, and no test patches
`time.time` — checked, because a patch that stops biting would leave them
green while exercising the real clock.

The checker was proven to bite in a throwaway repo rather than assumed from a
clean exit: it names a `while time.time() < deadline` poll and a
`time.time() - start` elapsed, and stays silent on the monotonic rewrite, on
an opt-out comment, and on `time.time() - path.stat().st_mtime` — where only
one operand is wall-clock-bound, so the comparison is absolute-vs-absolute and
correct.

Delete-check: The tempting deletion — ban time.time() outright and mint every stamp through
one helper — is wrong here: the wall clock is genuinely required at the four
boundary classes above, and reliability.py explains why a monotonic stamp
there would be a defect. So the dimension cannot be collapsed to one clock.
What IS deletable is the per-site judgement call: the free_router already
deletes it by INJECTING the clock (`clock=time.monotonic` at construction,
wall clock passed explicitly and justified where it differs). The rule
enforces the decidable half — an in-function wall-clock duration pair — and
the six sites are one-word fixes.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
Doctrine: `sed -n 88,98p aii_lib/src/aii_lib/free_router/router.py` -> `clock:
Callable[[], float] = time.monotonic`; `sed -n 138,150p .../reliability.py` ->
the WALL-clock exception comment verbatim at 143-145; `sed -n 82,98p
.../_transport.py` -> "Only the wall-clock DELTA is used, so it transfers
safely onto the router's monotonic clock" at 85-86. `git grep -c
'time.monotonic()' -- aii_lib aii_pipeline aii_runpod` -> 11 files summing to
32. All six cited wall-clock sites read directly: `grep -n 'time.time()'
repl_driver.py` -> 326,329,482,491,516,547,562,597,601; read 320-335 (bypass-
prompt watcher, 30 s deadline), 475-500 + 540-570
(turn_start/hard_cold_deadline/elapsed TimeoutError), 592-606 (/cost capture)
— all strictly in-process stall windows, and no comment at any of them
declares wall clock deliberate. `_verify.py:162/164` is an oauthAccount
rebuild poll; `usage.py:380/381` is a tmux /usage poll — both in-process.
`_turn.py:356` passes `runtime_seconds=time.monotonic() - started`, a
difference, so the inverse direction is clean as claimed.

Corrected statement of fact:
The count is the one soft spot: the same-function heuristic undercounts. I
enumerated every `time.time()` in package source (`git grep -n 'time\.time()'
-- aii_lib aii_pipeline aii_runpod aii_server aii_launcher claude_cred_manager
':!**/test_*.py'` -> 66 sites) and found at least three more in-process
duration families it cannot see, because the start is stored on an instance
attribute and read in a DIFFERENT method: (a)
`claude_oauth/_monitor/_loop.py:106` sets `self._rate_limit_start =
time.time()` and :232/:244 compute `int((time.time() -
self._rate_limit_start)/60)` — declared at `monitor.py:48`, never serialized;
(b) `utils/deploy_github/deployer.py:454/467` and :659/:682 —
`self._last_push_time` drives an in-process push rate limiter; (c)
`claude_cred_manager/src/claude_cred_manager/usage.py:223` (`time.time() - entry[0] < _CACHE_TTL_S`
over the in-memory `self._cache`) and :229/:238 (`self._fail_until` negative
cache). All four are in-process elapsed/TTL measurements on wall clock, i.e.
the same defect class. So build the rule's checker on 'a wall-clock value that
never reaches a serialization/subprocess/filesystem sink is compared or
subtracted', not on same-function pairs — otherwise it enforces 6 of ~10+ and
looks green while the cross-method cases drift. Dedupe is clean: no claimed
slug mentions monotonic/clock (rule-core-primitives covers naive-datetime
rejection at construction; rule-wire-timestamp-via-helper covers minting on
the wire).

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Preservation gate on a convention the repo already follows
deliberately (router clock defaults to time.monotonic, with the wall-clock
exception documented in reliability.py). A clock step turning an elapsed
negative silently disables a timeout; unclaimed (rule-wire-timestamp-via-
helper covers minting, not measuring).
- KEEP: AST-decidable: a duration or deadline computed from time.time() inside
one process. The repo already carries the doctrine in prose (router.py's clock
default, reliability.py's wall-clock exception comment), so the exception set
is written down rather than invented. Loud over a large non-empty population.
- KEEP: Delete-check is honest that the tempting deletion (mint every stamp
through one helper) is wrong — the wall clock is genuinely needed for stamps
crossing a process/disk/wire boundary, and reliability.py:143-145 already
documents that exception in prose. So the dimension is a judgment that recurs
at every new deadline, not a collapse. Unclaimed: no rule in the 383 covers …
