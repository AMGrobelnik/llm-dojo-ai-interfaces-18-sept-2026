<!-- hook: daemon-loop-stoppable -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# An interval-paced daemon-thread loop paces itself on its stop-Event and runs in a named thread — never `while True: time.sleep(interval)`, which nothing can interrupt

An interval-paced daemon-thread loop paces itself on its stop-Event
(`while not stop.wait(interval)`) and runs in a named thread — never
`while True: time.sleep(interval)`, which no test or clean shutdown can
interrupt. The house pattern additionally exposes a stop function that sets
the Event and joins the thread; the checker gates the two statically
decidable halves — pacing and naming — so the stop function is stated
guidance here, not part of the gate.

Current state (checker re-run 2026-09-10 over the six packages): **7 thread
targets, all Event-paced and named — zero violations, exit 0.** It was 13 on
2026-08-28, and none of the six that went away is a fix to this rule. FOUR are
the `no-new-daemon-threads` paydown, which converted run_cost_sweeper,
zombie_reaper, pod_discovery and redeploy_resume from daemon threads to
`@DBOS.scheduled` workflows and one `DBOS.start_workflow` (measured across that
change: 14 in-module thread targets before, 10 after). The remaining two moved
between 2026-08-28 and now for reasons this re-run does not identify — counted,
not attributed. The first three modules used to be this README's worked
examples of the house pattern; the pattern is unchanged, they are simply no
longer instances of it. What still is: apps.py:123,141-156
(`catalogue-refresh`, paced on `while not _refresh_stop.wait(interval_s)` with
`stop_catalogue_refresh` joining), credentials.py:535 (`claude-usage-poll`),
and claude_oauth/_monitor/_loop.py:73 (`while not self._stop_event.is_set()`)
with monitor.py:234-236 setting the Event and joining. The last pair's citation
was `_loop.py:71` / `monitor.py:202-206`; both had drifted, and re-reading them
is what this re-measurement is for.

Distinct from enforced rule-no-new-daemon-threads, which is a COUNT gate on
the web process gaining new loops — this pins the SHAPE of the loops that
legitimately exist, tree-wide including the ability-server process and
aii_lib. The two pull in the same direction: a thread the count gate removes
is one this rule no longer has to shape.

## History — the violation that motivated the rule (fixed 2026-08-28)

aii_server/agent_abilities/credentials.py:465-476 ran an UNNAMED daemon
thread as `while True: time.sleep(_USAGE_POLL_INTERVAL)` around a live usage
scrape, with no stop event; unstoppable in tests — the same genre as the
incident where concept-fig unit tests silently bought live API images
whenever an ability server answered. The Command section below records the
conversion; the checker has been green since.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: concurrency-async)

Command (checker implemented 2026-08-28):

    python3 $RULE_DIR/scripts/check_daemon_loop_pacing.py $(git ls-files '<the six packages>/*.py' | grep -v tests)

The checker is THREAD-TARGET aware: it resolves every `threading.Thread(target=fn)`
to `fn`'s body and judges only those, so a retry loop that sleeps
(`agent_abilities/retry.py`) or a request handler that polls (`api_get_usage`)
is not mistaken for a daemon. Measured 2026-08-28 over the six packages: 13
thread targets, ONE time-paced — the headline violation, `credentials.py:465`,
which by then already carried `name="claude-usage-poll"`; only the pacing was
left. Converted the same day to `while not self._usage_stop.wait(interval)`
with a `stop_usage_polling()` that sets the Event and joins the thread. The
verification's second candidate, `journal_writer.py`'s `while True:
self._queue.get()`, is a QUEUE-DRAINING loop whose shutdown idiom is a
sentinel, not an Event; it is outside this H1 ("interval-paced") and is
deliberately not judged by this checker.

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only | grep -qE '\.py$'`

Delete-check: The delete-form landed 2026-08-28 — the credentials.py poll
loop was converted to the Event pattern — so the stock is zero and the rule
now guards the shape against the next time-paced loop; nothing further to
delete. Queue-driven threads (journal_writer._run blocks on queue.get with
flush markers) are a different shape and out of scope by construction.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Explicit house pattern (three modules cite each other's Event-driven
shape), one live violator, and enforced rule-no-new-daemon-threads covers only
the web process gaining loops, not loop shape elsewhere. Narrow keep; convert
the credentials.py loop when landing.
- KEEP: One live violation against a three-site documented house pattern;
distinct from enforced no-new-daemon-threads (shape vs existence), and the
Event-paced form is what makes tests and shutdown not hang.
- KEEP: Event-paced shape is the documented house pattern at 4 sites with 1
straggler; detection must anchor on 'while True containing time.sleep in
package source' with a pinned allowlist — anchoring on threading.Thread
reachability is not statically decidable and would go vacuous. Distinct from
enforced rule-no-new-daemon-threads (web-process ban vs loop shape).

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Headline violation reproduced EXACTLY. `grep -n` on
aii_server/agent_abilities/credentials.py: 465 `while True:`, 466
`time.sleep(_USAGE_POLL_INTERVAL)` (=300.0, line 420), 475 `t =
threading.Thread(target=_poll_loop, daemon=True)` — no `name=`, no Event, no
stop function anywhere in the file. House pattern also reproduced:
run_cost_sweeper.py:189 `if _sweep_stop.wait(COST_SWEEP_START_DELAY_S)` /

Corrected statement of fact:
credentials.py:465-476 runs an UNNAMED daemon thread as `while True:
time.sleep(300)` around a live usage scrape with no stop Event — confirmed. It
is one of TWO such loops, not one: journal_writer.py:185/189 starts `aii-
journal-writer` on a `while True: self._queue.get()` body with no stop Event
and no shutdown sentinel. The 'Mirrors pod_discovery's Event-driven daemon-
thread pattern' quote is at zombie_reaper.py:334, not :344-357. Rule body
should state both violations and either scope to time-paced poll loops
(credentials only) or to any long-lived daemon loop (both).
