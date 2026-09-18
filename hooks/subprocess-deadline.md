<!-- hook: subprocess-deadline -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every subprocess interaction carries an explicit deadline, with post-kill reaps and pinned deliberately-unbounded interactive streams as the only exceptions.

In full: sync `subprocess.run` / `check_output` / `check_call` / `call`
passes `timeout=`, and async `proc.communicate()` / `proc.wait()` /
`readline()` sits under `asyncio.wait_for` — with post-kill reaps and the
pinned, deliberately-unbounded interactive streams as the only exceptions.

**State on 2026-08-28.** The built checker
(`scripts/check_subprocess_deadlines.py`) covers the SYNC half: an AST scan
over every tracked `*.py` in the six packages, tests excluded, exits 0 —
every sync call carries `timeout=` or sits on
`scripts/deadline_allowlist.txt` with a reason beside it (`tail -f --pid`,
`aii_public/sync.sh`, the image build+push: foreground jobs whose whole point
is to run as long as they take). The ASYNC half is NOT mechanized — the
checker's docstring defers it to "the async twin rule", and no such rule
exists in either tree — so it is measured by hand:
`aii_runpod/src/aii_runpod/deploy/_remote/_redeploy.py:208` (`docker
manifest inspect`) has been bounded by `_MANIFEST_INSPECT_TIMEOUT_S` since
2026-08-26, but `aii_launcher/src/aii_launcher/deploy.py:147` — `await
gh.communicate()` for `gh release create`, in a block whose own comment at
:109-114 calls it "never load-bearing", which a hang violates — still has no
deadline and no `asyncio.wait_for` anywhere in the file. Wrapping that one
call is the open fix; an async checker is the open mechanism.

The condition carries the `[ "$RULES_MODE" = all ] ||` escape (added
2026-08-28): without it the condition exited 1 in all-mode and `rules.py all`
skipped the rule permanently while its statement claimed every interaction.

## History (measurements before the checker existed)

Measured with an AST scan: 37 of 45 sync subprocess calls across the six
packages already carry timeout=; the 8 missing are
aii_lib/src/aii_lib/utils/tmux.py:88 and 446,
aii_launcher/src/aii_launcher/deploy.py:217 and 285, _deploy/_runpod.py:155,
_deploy/_local.py:79, 90 and 332 (the last is `tail -f --pid` — deliberately
unbounded, belongs on the script's pinned allowlist). Async side:
streaming.py:75, ssh.py:82 and relogin.py:410 are all correctly bounded, and
their bare `await proc.wait()` calls (streaming.py:78, ssh.py:87,
relogin.py:413) are post-kill reaps; the one genuine gap was _redeploy.py:188 —
`docker manifest inspect` reaches the registry over the network with no
deadline, inside the redeploy preflight, so a hung registry hangs the live-
redeploy path that rule-runpod-redeploy-safety otherwise guards.

**FIXED 2026-08-26, so this rule now arrives with nothing to fix.** That
lookup carries `_MANIFEST_INSPECT_TIMEOUT_S` (30 s) via `asyncio.wait_for`,
kills and reaps the hung child, and treats the timeout as INCONCLUSIVE
rather than blocking — matching the missing-docker-CLI branch beside it
instead of adding a second way for a redeploy to be blocked. Whether an
unreachable registry should instead BLOCK is a real question and an owner
call; it was deliberately not decided while adding the bound.
`test_missing_from_registry_bounds_a_registry_that_never_answers` pins the
deadline, the kill and the reap. Distinct
mechanism from the claimed rule-httpx-explicit-timeout (HTTP client kwarg) and
rule-watcher-net-calls-bounded (shell `timeout` wrapper in watcher scripts):
this is the Python subprocess API surface neither touches.

## Mechanism

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: concurrency-async)

Command (checker implemented 2026-08-28):

    python3 $RULE_DIR/scripts/check_subprocess_deadlines.py $(git ls-files '<the six packages>/*.py' | grep -v tests)

The proposal's command line said `git ls-files '*.py'`, i.e. the whole tree.
Measured 2026-08-28 that gives **203 unbounded of 259** — dominated by rule
checkers and `scripts/` tooling calling `git` locally, which is not the hang
the proposal argues (a deploy path waiting on a network or a pod). The
proposal's own MEASUREMENT was over the six packages, so the command follows
the measurement. Re-measured there the same day: 7 of 44 unbounded (one fewer
than above; `tmux.py:446` had been bounded since). Four were bounded in the
same change (pg.sh status/start, the launcher's `git`, `tmux kill-session`);
three are on `scripts/deadline_allowlist.txt` with their reasons — `tail -f
--pid`, `aii_public/sync.sh`, and the image build+push — each a foreground
job whose whole point is to run as long as it takes. The checker reports the
allowlist key beside every finding so exempting one is a one-line edit that
names the call, not the line number.

Condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only | grep -qE "\.py$"`

Delete-check: Delete-form was the plan and is done for the sync half: the 8 sync sites
are fixed or on the script's allowlist with a one-line reason each, and the
rule enforces the zero state — the check exists so the count stays zero, not
to babysit a backlog. The async half has one call left to bound
(`deploy.py:147`) and no checker yet.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: No ruff rule requires timeout= on subprocess.run (PLW1510 is check=,
not timeout), and the AST scan found 8 real unbounded sync sites plus one
async. Sibling of pending rule-httpx-explicit-timeout — same accepted
deadline-discipline shape for a different client. Fix the 9 sites when
landing, per its delete-form plan.
- KEEP: 9 real unbounded call sites measured, hangs are this repo's most-
documented failure obsession, and no ruff rule covers subprocess timeouts; AST
scan already prototyped, allowlist for the two deliberate streams is small.
- KILL: Wait — reversing: keep. (See corrected verdict below.)

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
HEADLINE NUMBERS REPRODUCE EXACTLY. I wrote my own AST scan
(scratchpad/scan_subproc.py, walking ast.Call over the six packages, tests
excluded) and it printed: 'SYNC subprocess calls: 45 with timeout= : 37
MISSING: 8'. The 8: _local.py:79, _local.py:90, _local.py:332, _runpod.py:155,
deploy.py:217, deploy.py:285, tmux.py:89, tmux.py:453. _local.py:332 is
`subprocess.run(["tail","-f",f"--pid={pi

Corrected statement of fact:
Corrected rule body: 45 sync subprocess.run/check_output/check_call/call sites
across the six packages, 37 already carrying timeout=, 8 without —
aii_lib/src/aii_lib/utils/tmux.py:89 and :453 (not 88/446),
aii_launcher/src/aii_launcher/deploy.py:217 and :285, _deploy/_runpod.py:155,
_deploy/_local.py:79, :90 and :332 (the last is `tail -f --pid`, an
interactive follow, allowlist it). Async side: streaming.py:75, ssh.py:82 and
relogin.py:411 (not 410) are bounded by asyncio.wait_for, and streaming.py:78
/ ssh.py:87 / relogin.py:414 (not 413) are post-kill reaps. There are TWO
unbounded network-reaching async subprocesses, not one: (a)
aii_runpod/.../_remote/_redeploy.py:188 — `docker manifest inspect` via `await
proc.communicate()` with no deadline, inside the Phase 0 preflight, so a hung
registry stalls the redeploy command though the fleet stays up; (b)
aii_launcher/src/aii_launcher/deploy.py:147 — `gh release create` via `await
gh.communicate()` with no deadline and no wait_for anywhere in the file, in a
block its own comment at :109-114 calls 'never load-bearing', which a hang
violates. Both fixes are a wrap in asyncio.wait_for; moderate risk because
both sit on the deploy path.
