<!-- hook: journal-wire-compat-manifest -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The journal's durable-read contract holds: no AnyMessage union member grows a required field beyond the committed per-model manifest, and BaseMessage keeps extra="allow"

In full: no AnyMessage union member grows a new required field beyond the
committed per-model required-fields map (rows minted by older writers must
re-parse forever), and BaseMessage keeps extra="allow"
(rows minted by newer writers must parse under older readers during a rolling
redeploy).

Journal rows outlive every deploy and are re-parsed through the typed models
on every serve: aii_lib/src/aii_lib/run/events/slim_wire.py:140-153 tries the
typed parse, falls back to BaseMessage.model_validate, then DROPS the row —
the code's own comment calls it 'a message the user never sees at all'. rule-
server-redeploy-preserves-runs makes mixed-writer journals the NORMAL case,
not an edge. Measured now: 42 AnyMessage union members carry required fields (parent_id
everywhere; ModuleStartMessage requires 4: name, parent_id, module_type,
attach_under_id) — a field made required in a refactor silently blanks or
degrades every pre-existing run's events view and nothing fails at commit.
extra="allow" is documented load-bearing at _messages/_base.py:37-38,58-59,
while the repo-wide push toward closed schemas (rule-config-models-closed-
schema, RunEventEnvelope's own extra=forbid at envelope.py:43) makes a well-
meant tighten-to-forbid edit on BaseMessage likely. No claimed rule covers
temporal schema evolution: rule-events-run-journal is the flow path, rule-
event-vocabulary-parity is FE/BE spelling parity of the CURRENT vocabulary.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: data-contracts)

Proposed command (implemented at approval):

    .venv/bin/python scripts/check_wire_compat.py  # import aii_lib.run.messages + envelope, compute {model: sorted(required model_fields)}, exact-diff against required_fields.yaml (growth = compat break, any drift = fail with the reason); assert BaseMessage.model_config['extra'] == 'allow'

Proposed condition: `git diff --cached --name-only -- 'aii_lib/src/aii_lib/run/' | grep -q .`


## IMPLEMENTED 2026-08-26 — `scripts/check_wire_compat.py` + `required_fields.yaml`

    .venv/bin/python $RULE_DIR/scripts/check_wire_compat.py

Arrives green: 42 union members, 59 required fields, `BaseMessage` still
`extra="allow"`.

**Scope: the union members only.** The script imports `AnyMessage` and
`BaseMessage` from `aii_lib.run.messages` — nothing else — and the manifest
pins exactly those 42 models. The envelope models (`RunEventEnvelope`,
`RunEventsResponse`, `RunEventCursorsResponse` —
`aii_lib/src/aii_lib/run/events/envelope.py`) are NOT in the census: the
proposal's command sketch named them, the implementation never built that
half, and the H1 and description claimed it until 2026-08-28, when the claim
was narrowed to what the mechanism measures. Whether envelopes deserve their
own pin is a separate question — they are minted per serve, not re-parsed
from durable rows, so the durable-read argument this rule rests on is about
the messages.

**The manifest is derived by IMPORTING the models, not by parsing source.**
Required-ness in pydantic is a property of the resolved field: no default, a
`PydanticUndefined` default, and an aliased field all read differently in text
and identically to `is_required()`. Regenerate the same way.

**`Annotated` proxies attribute access, and that produced a wrong census
first.** The union members are `Annotated[Model, Tag(...)]`, and
`hasattr(member, "model_fields")` returns **True** on the wrapper — so a guard
written as "unwrap only if it has no `model_fields`" never unwraps, while
`__name__` still reads `Annotated`. The first run gave 42 rows all named
`Annotated`. Unwrapping is now keyed on `get_origin(t) is Annotated`.

The opening previously said 45 — that figure counted the AnyMessage union
alias as a model — and now carries the 42 the mechanism measures.

Checked in both directions, which is what a durable-read contract needs: a
model that GROWS a required field fires, and so does a pinned model that has
left the union or a new member with no row — so the manifest keeps describing
the wire instead of drifting into a list nobody maintains.

Probed five ways: a grown requirement, a changed `extra`, a stale pin, and a
missing row all fire; the real pair does not.

Delete-check: The alternative is real schema versioning (envelope schema_version +
migrations on read) — far heavier machinery. The manifest pin IS the deleted
end-state of that machinery; if envelope versioning ever lands, this rule dies
into its migration tests.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Durable rows outlive every deploy and rolling redeploys need both
compat directions; no claimed rule pins required-field growth or extra=allow.
slim_wire.py's silent row-drop fallback makes a new required field an
invisible data loss. Genuinely new dimension (persisted-row schema
compatibility), high value.
- KEEP: Journal rows outlive every deploy and the drop-on-parse-failure path
is real (slim_wire.py); a required-fields manifest makes schema growth a
visible decision — the manifest-touch cost per model change is exactly the
intended friction. Distinct from wire-vocab-derived (values vs required-ness).
- KEEP: Durable-data compat is unguarded and rows outlive deploys; pydantic
introspection vs committed manifest is fully mechanizable and fails loudly on
any new required field. No overlap with enforced vocab-parity rules (#12/#37
cover vocabularies, not required-field growth).

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
File refs all hold exactly. `grep -n` on
aii_lib/src/aii_lib/run/events/slim_wire.py returns 140 `try:` / 141 `return
parse_message(slimmed), truncated` / 143-144
`BaseMessage.model_validate(slimmed)` / 148 `# a row dropped here is a message
the user never sees at all.` / 153 `return None, False` — 140-153 exact.
aii_lib/src/aii_lib/run/_messages/_base.py:37-38 is the docstring ``
``extra="allow"`

Corrected statement of fact:
Corrected statement for the rule body: 42 models are concrete members of the
AnyMessage discriminated union. Every one requires parent_id and type;
ModuleStartMessage requires four (name, parent_id, module_type,
attach_under_id). Not 45 — that figure counts the AnyMessage union alias as a
model. The two consequences must also be
separated, because they are different failures: a SUBCLASS gaining a required
field DEGRADES an old row to an untyped bare BaseMessage (verified:
ModuleStartMessage minus attach_under_id parses as BaseMessage), which rule-
events-run-journal's test docstring already names as the fallback's designed
job; only a tighten on BaseMessage itself (a new required field there, or
extra="forbid") reaches the DROP at slim_wire.py:153. The uncovered half is
the second one.
