<!-- hook: config-duration-keys-carry-seconds-suffix -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep, RULES_MODE
# Every duration-valued key added to tracked aii_config YAML names its unit in the key — a suffix like `_s`, `_ms`, `_seconds` — no bare `agent_timeout:`, no unit living only in a trailing comment

Implemented and green: `scripts/check_config_duration_units.py` gates every
ADDED duration key at commit and states the stock in all-mode — measured
2026-08-28: 70 duration keys, 14 name their unit, 56 do not (see IMPLEMENTED
below). The suffixes the checker accepts as naming a unit are the seconds
family (`_s`, `_sec`, `_secs`, `_seconds`), `_ms`, and the minutes/hours
families (`_m`, `_min`, `_minutes`, `_h`, `_hours`) — naming the unit is the
invariant, not one blessed unit.

## The original proposal (2026-08-24 measurements — superseded by IMPLEMENTED below)

RAN a scan over `git ls-files aii_config` matching duration-noun keys and
classifying by unit suffix: `unit-suffixed keys : 7 sites / 6 distinct ->
{'initial_delay_s': 2, 'check_interval_seconds': 1, 'launch_stagger_s': 1,
'rescan_backoff_s': 1, 'metrics_interval_ms': 1, 'trace_export_interval_ms':
1}` and `bare keys : 55 sites / 9 distinct -> {'agent_timeout': 30,
'pod_timeout': 15, 'max_notebook_total_runtime': 2, 'push_timeout': 2,
'min_push_interval': 2, 'message_timeout': 1, 'healthcheck_timeout': 1,
'min_backoff': 1, 'max_backoff': 1}`, with `bare WITH a trailing unit comment:
27 bare with NO comment: 28`. So the same dimension is spelled FOUR ways in
one config tree: `_s`, `_seconds`, `_ms`, and bare — and two different units
are in play with no key-level signal (`metrics_interval_ms: 300000` beside
`check_interval_seconds: 660` beside `agent_timeout: 7200`). The 27 trailing
comments are the tax the missing suffix charges:
`aii_config/pipeline/pipeline.yaml:224` reads `pod_timeout: 14400 # 240 min
pod lifetime`, while `aii_config/frontend/config.yaml:65` carries the SAME key
and SAME value `pod_timeout: 14400` with no comment at all — verified side by
side in the scan output. The Python side already names its units
(`aii_pipeline/src/aii_pipeline/prompts/components/time_budgets.py:10` `def
_fmt_minutes(seconds: int | None)`, and `invention_loop.py:29 agent_timeout:
int` is only knowable as seconds by reading that `// 60`), so the unit is
known everywhere except where a human or agent edits it. Honest scope note: I
checked whether this is really the whole story on the Python side and it is
not — RAN an AST scan of time-noun identifiers across the six package trees:
`time-noun names: 450 without unit suffix: 258`, so a matching Python-
identifier rule would be a 258-site refactor and I am NOT proposing one; 55
sites over 9 keys in tracked YAML is the tractable half, and it is the half a
human actually edits.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: time-and-clocks)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_config_duration_units.py   # regex over `git ls-files aii_config` for duration-noun keys with a numeric value; fails any key not ending in `_s`. Verified today: exits naming the 55 bare sites plus metrics_interval_ms, trace_export_interval_ms and check_interval_seconds.

Proposed condition: `git diff --cached --name-only -- 'aii_config/**/*.yaml' | grep -q .`

Delete-check: Yes — this is a delete, not a policing. Pin ONE unit (seconds) and one
spelling (`_s`): rename the 9 bare keys, convert the 2 `_ms` keys to `_s` with
the ×1000 pushed to the OTel boundary that needs millis (`jsonl_exporter.py`'s
`timeout_millis`), normalise `check_interval_seconds` -> `_s`, and then DELETE
the 27 explanatory trailing comments, because the key answers the question
they exist to answer. Twelve field renames total. Named cost the owner should
weigh: a per-run `config_snapshot` is persisted in DBOS and replayed by
fork/resume, so the renamed pydantic fields need a deserialisation alias for
old snapshots — that is an adoption detail, not a second sanctioned spelling,
and the rule checks the tracked YAML keys, which is where authoring happens.
(Superseded in part by the IMPLEMENTED section below: the shipped checker
deliberately KEEPS the 2 `_ms` keys — the OTel exporter's API is
milliseconds — and the stock renames are owner-gated; naming the unit is the
invariant, forcing one unit is not.)

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **partly-wrong**.
A different agent re-ran every measurement before this reached the owner.

What it found:
RAN my own AST-free scan over `git ls-files aii_config` (18 files), matching
`^\s*([a-z][a-z0-9_]*)\s*:\s*([0-9][0-9_.]*)\s*(#.*)?$` on duration-noun keys
and classifying by unit suffix -> `SUFFIXED 15 sites / 11 distinct
{'timeout_s': 3, 'interval_s': 2, 'initial_delay_s': 2,
'check_interval_seconds': 1, 'min_token_validity_seconds': 1,
'launch_stagger_s': 1, 'rescan_backoff_s': 1, 'metrics_interval_ms': 1,
'trace_export_interval_ms': 1, 'token_refresh_threshold_seconds': 1,
'timeout_secs': 1}` and `BARE 56 sites / 10 distinct {'agent_timeout': 30,
'pod_timeout': 15, 'max_notebook_total_runtime': 2, 'push_timeout': 2,
'min_push_interval': 2, 'message_timeout': 1, 'healthcheck_timeout': 1,
'timeout': 1, 'min_backoff': 1, 'max_backoff': 1}`, `bare with comment 27 no
comment 29`. Spot-checks all confirmed:
`aii_config/pipeline/pipeline.yaml:224:pod_timeout: 14400 # 240 min pod
lifetime` beside `aii_config/frontend/config.yaml:65:pod_timeout: 14400` with
no comment. RAN `git grep -nE 'metrics_interval_ms|check_interval_seconds|time
out_secs|timeout_s:|interval_s:' -- aii_config` ->
`aii_config/pipeline/io/sinks.yaml:33: metrics_interval_ms: 300000`,
`aii_config/pipeline/harness/agent_backend.yaml:135: check_interval_seconds:
660`, `aii_config/server/server.yaml:100: timeout_secs: 10`,
`aii_config/dbos_run.yaml:20: timeout_s: 10.0`. Python side:
`aii_pipeline/src/aii_pipeline/prompts/components/time_budgets.py:10:def
_fmt_minutes(seconds: int | None) -> str:` confirmed; `grep -n 'agent_timeout:
int' aii_pipeline/src/aii_pipeline/utils/config_models/invention_loop.py` ->
`29: agent_timeout: int | None = 7200` confirmed.

Corrected statement of fact:
Direction holds and is understated, but two quoted counts do not reproduce.
Suffixed is 15 sites / 11 distinct, NOT 7 / 6 — the proposal's scan missed
aii_config/dbos_run.yaml entirely (timeout_s x3, interval_s x2) plus
min_token_validity_seconds and token_refresh_threshold_seconds
(agent_backend.yaml:153, abilities.yaml:16-ish). Bare is 56 / 10, not 55 / 9 —
it missed `aii_config/server/abilities.yaml:9 timeout: 180` (a bare `timeout:`
whose unit lives in a comment ABOVE it, not trailing, which is a third
comment-placement variant). And the headline 'spelled FOUR ways' is wrong:
there are FIVE — `_s`, `_seconds`, `_secs` (aii_config/server/server.yaml:100
`timeout_secs: 10`), `_ms`, and bare. Rewrite the evidence with the
reproducible numbers; the case gets stronger, not weaker. Also note for
scoping: `min_backoff: 1.0` / `max_backoff: 20.0` (abilities.yaml:15-16) are
floats, so a naive `*_s` rename rule must not assume integer seconds.

Filter verdicts (3-lens adversarial, kept 2/3):
- KILL: Naming cosmetics with no measured incident in this repo; enforcement
means renaming 9 keys across yaml plus their pydantic readers, then a gate
that bites every new config key. Units are already visible at the typed model.
- KEEP: Implementable as a numeric-valued-key scan over 18 tracked yaml files
with a written-down duration-noun regex; the *_ms ban half is exact. Fails
open only for nouns outside the regex — a bounded, declarable limitation, not
a silent empty match, and the file count is the floor.
- KEEP: A naming convention is the one thing a collapse cannot make
unrepresentable: after renaming the 9 bare keys and converting the 2 `*_ms`,
the very next added key is still a bare `timeout: 30` unless something says
otherwise. The repo already carries this genre as ENFORCED rule-canonical-
nouns (domain nouns) — this is the units half, unclaimed. A unit that lives
only in a …

OWNER-GATED: the STOCK only — the implemented gate covers additions and is green today. Making the 56 bare stock keys green requires renames whose pydantic readers are replayed from DBOS-persisted config snapshots, so they need deserialisation aliases for old snapshots; that backlog stays the owner's.

## IMPLEMENTED (2026-08-26) — gates additions, states the stock

`scripts/check_config_duration_units.py`. Re-measured 2026-08-28 across the
18 tracked config files: **70 duration keys, 14 name their unit, 56 do not**
— of which 27 carry a trailing unit comment and 29 carry nothing. The 14 use
FOUR spellings: `_s`, `_seconds`, `_secs`, `_ms`; the checker's `NAMES_UNIT`
also accepts `_sec`, `_m`, `_min`, `_minutes`, `_h` and `_hours`, none of
which the stock uses yet. (The 2026-08-26 measurement read 69 keys / 13
named; the one key added since, `probe_timeout_s` in `3c59b16d1`, names its
unit — the gate doing its job.)

(The body's earlier figures — 7 suffixed, 55 bare — were close but the scan that
produced them anchored on the duration noun at the END of the key, which misses
`initial_delay_s` entirely. My own first re-measurement repeated that mistake and
reported 0 suffixed keys. The regex now allows a suffix after the noun.)

**It gates ADDITIONS, not the stock, and that is arithmetic rather than
timidity.** Renaming 56 keys means changing every consumer — pydantic models,
defaults, overlays and the private files a fresh machine copies — a refactor
with a real chance of a silent unit error partway through, which is the exact
failure this rule exists to prevent. The backlog stays the owner's.

At commit it reads only ADDED lines. In all-mode it prints the stock and exits
0, labelled advisory, in the same shape `rules-grep` uses for stock drift — so a
clean exit never reads as "the backlog is gone".

**`_ms` is accepted, not only `_s`, and the title now says so.**
`metrics_interval_ms` and `trace_export_interval_ms` are milliseconds because
the OpenTelemetry exporter's API is; renaming them to seconds would put the
repo's vocabulary at odds with the library it configures. Naming the unit is the
invariant that matters — forcing one unit is not.

Probed six ways: a bare key is caught, a bare key WITH a trailing comment is
still caught (the comment is the tax, not the fix), `_s` and `_ms` pass, and
non-duration keys and non-config files are ignored.
