<!-- hook: loguru-diagnose-off -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every loguru sink configured in workspace package source passes diagnose=False — a traceback never renders local variable values into a log line

aii_lib/src/aii_lib/claude_oauth/accounts_health.py:279-288 is the ONE
compliant site and states the reason in its docstring ('diagnose=False keeps
loguru from rendering local variable values into tracebacks — the SMTP
credentials must never reach a log line'). The other three sink sites run on
loguru's diagnose=True default: aii_server/config/settings.py:602 (stderr) and
:634 (the serialize=True, level=DEBUG jsonl that settings.py:590-591 says
'lives on the persistent volume so it survives pod restarts' — the same shared
volume settings.py:466-469 notes agent worker pods mount), and
aii_pipeline/src/aii_pipeline/_cli/setup.py:48. Server frames hold decrypted
user API keys and Claude credential blobs (claude_oauth/*, user-key
endpoints); one exception through those frames serializes the values into
aii_server.jsonl on the shared volume. Distinct from pending rule-loguru-sink-
single-source (pins WHERE sinks are configured and one format, not their
kwargs) and from killed rule-loguru-only-shared-src (which was about a second
logging framework, not sink kwargs — different mechanism entirely).
Credential-hygiene parity: the repo already recognized this hazard once and
fixed it at the lowest-risk sink only.

Mechanism (implemented 2026-08-26, `scripts/check_diagnose_off.py`):

    .venv/bin/python $RULE_DIR/scripts/check_diagnose_off.py

**The finding above is STALE and the rule arrives green.** It recorded one
compliant site against three on loguru's default. Re-measured: all FOUR sinks
now pass `diagnose=False` — `accounts_health.py:283`, `_cli/setup.py:51`, and
`settings.py:609` and `:676` (cited above as 602 and 634; both moved). The
other three were fixed in the interim, so what is left is regression pressure,
which is what a gate is for.

**Two sink forms, and checking only the common one fails open.**
`logger.add(...)` is what this tree uses today, but loguru also accepts
`logger.configure(handlers=[{...}])`, where each dict is a sink specification
— a form that would install sinks the check never saw. There is no instance of
it here, which is precisely why it is covered now rather than after one
appears: a checker steppable around by a supported API has a published bypass.
A `handlers` entry that is not a literal dict is reported rather than skipped,
since "cannot judge it" must not read as "fine".

`logger.configure(patcher=...)` is NOT a sink form and is left alone —
`run/sinks/otel/log_correlation.py` uses it to attach trace ids.

Probed seven ways: a bare `logger.add`, an explicit `diagnose=True`, and a
`configure(handlers=[…])` without diagnose all fire; `diagnose=False` in both
forms, a `patcher=` configure, and a sink under `/tests/` do not.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: operational-runtime)

Proposed command (implemented at approval):

    python $RULE_DIR/scripts/check_diagnose_off.py  # AST-walk every logger.add(...) call in aii_lib/aii_pipeline/aii_server/aii_launcher/aii_runpod/claude_cred_manager package source (tests excluded); fail listing any call without an explicit diagnose=False keyword

Delete-check: The sinks cannot be deleted — they are the observability story
(settings.py:590 'colored stderr for humans + rotating JSONL for
replay/grep'). Nor does consolidation delete the dimension: if pending rule-
loguru-sink-single-source lands, sink config collapses to one shared helper
and this check narrows to that helper's logger.add calls — the invariant
survives the collapse and keeps guarding it.

That prediction came true on 2026-09-04: the four hand-rolled blocks are now
`aii_lib/src/aii_lib/logging_setup.py`, this check finds its two sinks there,
and both still pass `diagnose=False`. The only edit the collapse forced was
the non-vacuity floor the third filter verdict above asked for — `_MIN_SINKS`
3 -> 2, since the tree genuinely shrank and a floor left at 3 would have read
the cleanup as a broken parse.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Distinct credential-hygiene property no claimed rule states:
diagnose=True renders local variable values (incl. credentials) into
tracebacks. Not location (pending rule-loguru-sink-single-source) nor
boundedness (rule-telemetry-sinks). One cheap ban-grep, three live non-
compliant sinks, and the compliant site's docstring already states the
rationale. If loguru-sink-single-source lands, …
- KILL: Real credential-hygiene invariant (verified: accounts_health.py:288 is
the lone compliant sink), but pending rule-loguru-sink-single-source already
collapses sink config into one helper — fold 'the helper declares
diagnose=False' into that rule's check instead of a second loguru scanner over
the same lines. [merge->rule-loguru-sink-single-source]
- KEEP: Mechanizable AST scan over logger.add kwargs; distinct from pending
rule-loguru-sink-single-source (location vs property). Non-vacuity
requirement: the scan must assert >=1 sink found or fail — an empty glob
passing silently is exactly the early-rules trap.

STATUS (2026-08-22): the three non-compliant sinks are FIXED — all four
`logger.add` sites in workspace source now pass `diagnose=False`
(AST-verified). The premise was proven empirically first, because the
obvious probe is misleading twice over: loguru can only annotate values
when it can READ THE SOURCE FILE, so a probe piped through stdin shows
no leak regardless of the flag, and a sink whose format is `{message}`
alone renders no traceback at all. Run from a real file, both sink
shapes (plain and `serialize=True`) rendered a local's value with the
default and did not with the flag. The rule remains worth approving as
the guard: a new sink added tomorrow inherits the leaky default.
