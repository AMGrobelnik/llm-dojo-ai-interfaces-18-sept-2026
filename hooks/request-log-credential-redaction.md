<!-- hook: request-log-credential-redaction -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A plaintext credential posted to the API never survives into a request-log line

A plaintext credential posted to the API never survives into a
request-log line: middleware redaction provably covers every
credential-carrying wire field, derived from the actual schemas
(SaveApiKeysRequest, VerifyKeyRequest) rather than a hand-list — or the
endpoint sits on a no-body-summary path list.

CONFIRMED live gap, executed during this review (since fixed — see below):
SaveApiKeysRequest names its
plaintext key fields 'openrouter' and 'serper'
(dashboard/api/user_settings.py:73-74); _REDACT_KEYS
(agent_abilities/middleware.py:22-40) is exact-name matching and lacks both,
so _redact returns {'openrouter': 'sk-or-v1-SECRETSECRETSECRET', ...} verbatim
(measured — only the 'key' field scrubs). _summarize_dict truncates values at
AII_LOG_TRUNCATE_CHARS=200 (settings.py:44), longer than a real provider key,
so the FULL key lands in the log line, and the DEBUG JSONL sink persists it on
the shared volume across pod restarts (settings.py:633-640). Not covered
elsewhere: rule-server-user-api-keys pins at-rest encryption + response hint
hygiene, rule-events-run-journal redacts the run-event path, rule-server-
events-poll-feed's tests import _redact but assert poll DEMOTION only. The
middleware's own comment history shows the hand-list already needed a retrofit
once (the allauth 'key' field, middleware.py:27-30).

Mechanism (implemented 2026-08-26, `scripts/check_credential_field_redaction.py`):

    .venv/bin/python $RULE_DIR/scripts/check_credential_field_redaction.py

**The live gap this body describes is FIXED — `799529b38` — so the rule
arrives green.** It was real, and confirmed by execution rather than reading:
`_redact` returned a 57-character provider key VERBATIM while `api_key` beside
it scrubbed, and `_summarize_dict` truncates at 200 characters, well above
that. `openrouter` and `serper` are now in `_REDACT_KEYS`.

That fix is a hand-edited list, which cannot cover the NEXT provider — the
dimension this mechanism closes. It derives the expected names from the two
places that define them rather than restating them:

- `_PROVIDERS` in `user_settings.py` is the wire vocabulary the save and
  verify handlers iterate. A provider added there without a redaction entry is
  precisely the defect that already happened once.
- `SaveApiKeysRequest`'s own `str`-annotated fields catch a credential field
  that is NOT provider-named. The `*_enabled` ticks are `bool | None`, so the
  ANNOTATION separates keys from switches without a name convention that has
  to be kept in step.

Both are read with `ast`, not imported: importing `user_settings` pulls in
Django settings and a configured app registry, which would make this fail for
reasons that have nothing to do with redaction. `_REDACT_KEYS` is a
`frozenset({...})` CALL rather than a bare literal, so the set argument is
evaluated specifically — `literal_eval` on the call raises, and swallowing
that would yield an empty set and report every field as unredacted.

Measured: 2 providers, 2 plaintext schema fields, 14 redaction keys, all
covered. Probed five ways: a new provider without an entry and a new
plaintext field that is not provider-named both fire; a provider added WITH
its entry, a `bool` `*_enabled` tick, and the current tree all stay quiet.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: access-parity)

Proposed command (implemented at approval):

    .venv/bin/python $RULE_DIR/scripts/check_credential_field_redaction.py  # build sentinel-valued bodies from the credential-carrying schemas' field sets, run middleware._redact, fail if any sentinel survives and the route is not on the no-body-summary list

Proposed condition: `none — pure-function import test, sub-second`

Delete-check: Partly — the stronger deletion is to stop parsing credential-bearing bodies
for logging at all: add /api/settings/api-keys to the middleware's skip list
(the poll-path mechanism already exists, middleware.py:130+), deleting the
redact-this-field bookkeeping for that route. The check accepts either end-
state: on the skip list, or provably redacted.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: CONFIRMED live gap executed during review: plaintext openrouter/serper
keys survive _redact into request logs because _REDACT_KEYS is a hand-list
that lags SaveApiKeysRequest's schema. Deriving coverage from the schemas
kills the hand-list drift class. Enforced rule-server-user-api-keys covers
storage/wire hints, not the log middleware. High value; also adopt its no-
body-summary deletion …
- KEEP: CONFIRMED live gap executed during review: plaintext openrouter/serper
keys survive _redact into request logs; deriving the redaction set from the
actual schemas kills the hand-list drift class permanently. Credential
hygiene, high value, cheap check.
- KEEP: Gap re-verified now: middleware.py contains neither 'openrouter' nor
'serper'. Schema-derived coverage (pinned credential-schema class list, fields
introspected) beats the hand-list it audits; note the class list itself is the
residual open-world edge — a field-name heuristic sweep should back it.
