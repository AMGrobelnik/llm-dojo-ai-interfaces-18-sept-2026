<!-- hook: cancel-then-await -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A function that creates and cancels an asyncio task awaits it after the cancel (CancelledError suppressed), so cancellation completes instead of dangling.

Cancellation completes, never dangles: a function that creates an asyncio
task and cancels it awaits it after the cancel (CancelledError suppressed).
The proposal carried a second half — an `except asyncio.CancelledError`
inside a loop exits the loop (raise/return/break) rather than continuing
another iteration — which the implemented check does NOT enforce; the
handler census below is evidence of discipline, not of enforcement (see
IMPLEMENTED).

The cancel→await→suppress shape is the house pattern at 8+ sites
(aii_pipeline/src/aii_pipeline/pipeline.py:508-512;
aii_lib/.../terminal_claude_agent/_agent/_run.py:724-729;
aii_runpod/src/aii_runpod/pod_infra/worker_pod.py:473-478 and 598-603;
claude_cred_manager/src/claude_cred_manager/serve.py:176-178 and 236-239), and
event_pump.py:117 states the contract explicitly: 'caller owns cancel/await'.
That violation is FIXED, and this rule now ships at zero stock. It read "one
live violation today: sdk_openhands_agent/_agent/_turn.py:354 cancels the
pump's drainer task and never awaits it". Commit `487cf9261` ("the event
drainer is awaited after cancel, like its sibling") closed it; the site is now
`_turn.py:359-365` and carries the full cancel→await→suppress shape with a
comment explaining why a bare cancel returns before the task has stopped.

Re-measured 2026-08-24: no first-party site cancels an asyncio task without
awaiting it. That changes what approving this costs — per the engine's own
guidance a rule at zero stock can ship whole-tree (`--tree`) immediately
rather than added-lines-only, so it would guard the pattern everywhere from
the first commit instead of only where someone happens to edit.

Note for whoever re-measures: a naive "await within the next few statements"
scan reports false positives. `terminal_claude_agent/_agent/_run.py:724`
cancels in one `for` loop and awaits in the next, which is compliant and is
cited above as the house pattern — any checker needs to see the whole
function, not a window. The loop half pins currently-perfect discipline across
all 20 handlers (message_poller.py:106 returns, streaming.py:154 breaks,
orchestrator_client.py:452 returns, pod_launcher.py:475 raises,
runpod_message_forwarder.py:170/176/184 re-raise); a swallowed cancel in a
loop is exactly what makes /stop hang until safety_net.py's outer kill lands,
which its docstring says leaves 'on-disk state indistinguishable from a
crash'.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: concurrency-async)

Superseded proposal — the script it names was never written, and its
condition differs from the one the frontmatter runs; the implemented
command is documented under IMPLEMENTED below:

    python3 scripts/check_cancellation_discipline.py $(git ls-files 'aii_*/**/*.py' 'claude_cred_manager/**/*.py' | grep -v test)
    # proposed condition: git diff --cached --name-only | grep -qE '\.py$'


## IMPLEMENTED 2026-08-26 — `scripts/check_cancel_then_await.py`

    .venv/bin/python $RULE_DIR/scripts/check_cancel_then_await.py

Arrives green. The rule's zero-stock claim holds, but only once the check is
scoped the way the rule's own sentence is — and the first version was not.

**It reported two sites, and BOTH were my error, not the tree's:**

| site | why it is correct |
|---|---|
| `pod_launcher.launch_race` | awaits `gather(*tasks.values())` |
| `run_jobs.cancel_in_flight_jobs` | cancels tasks it did not own |

The first is a COLLECTIVE await: every task is awaited, just not one at a time,
and a per-name check calls that a defect. The second is the scoping the rule
states and I had dropped — "a function that **creates** an asyncio task and
cancels it". A function cancelling tasks pulled from a registry cannot await
their lifecycle; their own `finally` blocks unregister them elsewhere. Demanding
an await there would report correct code forever.

So the check now fires only inside functions that mint a task
(`create_task`/`ensure_future`/`start_soon`), and treats `gather`/`wait` as
satisfying the await.

**The implemented scope is the cancel→await half ONLY.** The script walks
`.cancel()` calls in task-minting functions and looks for a matching
await/gather; it contains no `except CancelledError` handler analysis, so
the loop half of the original proposal (a handler in a loop must
raise/return/break) is not built. The H1 and description claim only what
the script checks; the loop half stays recorded here as an unbuilt
extension an approver may ask for.

The receiver is matched as an EXPRESSION, not a bare name — these tasks are
usually attributes, and `self._drainer.cancel()` must pair with
`await self._drainer`.

Probed six ways: the rule's own shape (create, cancel, never await) and an
attribute-held task left unawaited both fire; a cancel-then-await, an
attribute-held task that is awaited, the collective-gather shape, and a cancel
of a task the function does not own all pass.

Delete-check: The dimension cannot be deleted — cooperative cancellation is the mechanism
behind /stop, fork, and redeploy-resume (rule-pipeline-stop-crash-recovery
depends on it landing). The violation this line used to say "gets fixed as
part of landing the rule" was fixed independently by `487cf9261`, so landing
the rule now costs no code change at all; cross-owner cancels like
run_jobs.py:356 (task owned by another driver whose finally does the
bookkeeping) are excluded by scoping the check to tasks created in the same
function.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: House pattern at 8+ sites, and the failure mode (cancel that never
lands, or a loop that survives its own CancelledError) is a hang class no
linter covers — ruff has RUF006 for dangling tasks but nothing for cancel-
without-await or continue-after-CancelledError. Behavior rules (stop-crash-
recovery) test outcomes; this pins the source shape that produces them.
- KEEP: House pattern at 8+ sites guarding a real hang class (dangling
cancels, CancelledError-swallowing loops) that no ruff rule covers; AST check
over a narrow shape is feasible and stop/fork/redeploy correctness rides on
it.
- KEEP: Half (b) — except CancelledError in a loop without raise/return/break
— is a clean AST check. Half (a) needs a per-function visitor with an
allowlist for cross-function ownership (task stored on self); implementable
but must fail loud on unmatched .cancel() rather than skip. 8+ conforming
sites prove the pattern is house style.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds, census grown.**

`except (asyncio.)CancelledError` handlers: **21** across 14 files, against
the stated 20. Growth, not decay. All five cited modules still exist —
`message_poller`, `streaming`, `orchestrator_client`, `pod_launcher`,
`runpod_message_forwarder`.

Method note: "handlers" here means CancelledError handlers, not request
handlers. A first pass measured task-creating files (15) and `.cancel()`
calls (5) and matched neither — the numbers looked like a large
discrepancy and were simply answering a different question.
