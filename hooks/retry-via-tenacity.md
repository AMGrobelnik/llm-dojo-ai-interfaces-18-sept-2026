<!-- hook: retry-via-tenacity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Retries are the tenacity decorator in the house shape — not a loop

New `for attempt in range(…)` retry loops are blocked (added lines only;
the 29 in the stock are the advisory backlog). The sanctioned pattern, verbatim
from `ability_client.py` / `claude_oauth/usage.py`:

    @retry(
        retry=retry_if_exception_type(<YourTransientError>),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        before_sleep=make_retry_log(label="<what>"),
        reraise=True,
    )

Plus: every httpx call carries an explicit `timeout=` (a computed deadline
where one exists — see `_timeout`/`HTTP_TIMEOUT_HEADROOM` in
ability_client). Retrying is classification (which exceptions are
transient), budget, backoff, and logging — four decisions the decorator
states declaratively; a hand loop re-decides them ad hoc and usually
forgets one.

Scope note: agent-turn validation retries are a DIFFERENT domain with
their own shared skeleton (`retry_until_valid` in
agent_backend/_shared/core/retry.py) — use that there, tenacity for I/O.
That file is excluded from the pathspec by name: its implementation loop
(retry.py:53) IS the sanctioned skeleton — the one `for attempt in
range(...)` this rule prescribes rather than bans — so a commit touching
it is never blocked by this gate.

Fix when blocked: wrap the call in the decorator above; if the loop is
genuinely not a retry (batch pagination etc.), rename the loop variable —
the pattern matches retry-intent names iterating `range(...)` only, so
tenacity's own `async for attempt in AsyncRetrying(...)` idiom
(ability_client.py:401) and docstring prose (the `retry_until_valid`
skeleton sketch in agent_backend/_shared/core/retry.py) never match it.

Trap before you write a custom `wait=`: **tenacity evaluates the `wait`
callable BEFORE it checks `stop`.** So a wait that indexes a fixed schedule by
`attempt_number` is evaluated once more than it has slots, and raises
`IndexError` on the final attempt — an error the decorator does not convert
into a `RetryError`, so it escapes to the caller and reads like a bug in the
retried function.

Verified against the installed tenacity (9.1.2), not taken on trust.
`_post_retry_check_actions` queues the two in this order, and `iter` runs the
queue in order:

    406        self._add_action_func(self._run_wait)
    407        self._add_action_func(self._run_stop)

A three-slot schedule with `stop_after_attempt(3)` and
`wait=lambda rs: SCHEDULE[rs.attempt_number]` raises
`IndexError: list index out of range`, with `wait` recorded as called on
attempts `[1, 2, 3]`. The value the final attempt computes is then thrown
away: `_post_stop_check_actions` returns as soon as `stop` fires, before
`next_action` — the only consumer of `upcoming_sleep` — is queued. Measured:
a schedule whose third slot is 5 s finishes in 0.022 s.

| callback | queued | runs on the final attempt |
|---|---|---|
| `wait` | before `stop` | yes, and the value is dropped |
| `before_sleep` | after `stop` | no |

Which is why the house shape above is unaffected: `make_retry_log` is a
`before_sleep` callback (`aii_lib/src/aii_lib/utils/retry.py:41` reads
`attempt_number` there), and that one is queued only when a sleep is actually
going to happen. Every `wait=` in the repo today is `wait_exponential` or
`wait_fixed`, so nothing here carries the fragile shape — this is a note for
the next person tempted to hand-roll a schedule.

Delete-check: cannot delete — transient failure exists; one idiom instead
of five (tenacity, backoff, manual loops ×29) is the point.
