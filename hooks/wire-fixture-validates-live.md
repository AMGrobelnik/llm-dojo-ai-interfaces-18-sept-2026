<!-- hook: wire-fixture-validates-live -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every wire-shaped fixture under tests/fixtures/ stays wire-true

Every wire-shaped fixture under tests/fixtures/ stays wire-true: each entry
in a fixture's events array validates through the live
TypeAdapter(RunEventEnvelope) and resolves to a concrete message type —
parity tests must fold event shapes the journal can actually carry, not a
hand-typed dialect.

STATUS: implemented 2026-08-26 as `scripts/check_wire_fixtures.py` (in this
rule's directory) and green — 12 of 12 entries in
`tests/fixtures/run_cost_parity.json` validate against the live envelope
model (re-run 2026-08-28, rc=0). The defect it was proposed from — 5 of
those 12 omitting the REQUIRED `parent_id` — was repaired by `0c9711c84`
("the cost-parity fixture is wire-true again", 2026-08-22), two days after
`c509ff509` created the fixture stale. The rule is the guard against a
second such birth: nothing else stops the next fixture from being hand-typed
into a shape no producer emits, because both readers —
research-monorepo/unit-tests/cost-accounting/test_run_cost_parity.py and
aii_frontend/features/labs/__tests__/run-cost-parity.test.ts — feed the raw
dicts straight to the reducers with no model validation. Distinct from
rule-parity-fixture-two-readers, which only requires both sides to READ the
fixture and says nothing about the fixture matching its producer's schema.

## What the check proves (2026-08-26)

**The entries are ENVELOPES, not messages, and confusing the two reads as a
defect.** Looking for `type` or `parent_id` at the top level finds neither: 0
of 12 entries carry a top-level `parent_id`, and 12 of 12 nested messages do.
The implementer made that mistake first and it briefly looked like a finding.

**Validation is DEEP** — the envelope's `message` field is the `AnyMessage`
union, proven by removing a nested `parent_id` and watching the envelope fail
with `message.agent_summary.parent_id`.

**But validation alone proves parseability, not typed-ness.** An unknown
`type` does NOT fail — it resolves to `BaseMessage`, deliberately, because a
row from a newer writer must parse under an older reader during a rolling
redeploy. So each entry must also resolve to a CONCRETE union member.

That surfaced one entry, and it is a design question rather than a defect.
Entry 10 declares `agent_message`, which is not among the 42 union tags (the
near-match is `agent_message_delta`). It is the decoy: `total_cost=99.0`
against an expected total of `5.44`, so it exists to be ignored, and
`test_run_cost_parity.py:63` asserts on the SET of message types — renaming
it would change what the fixture proves. Recorded as an exemption
(`FALLBACK_ALLOWED`) carrying that evidence, checked BOTH ways: if it ever
resolves concretely, the entry fails as stale.

Probed five ways: a missing nested field, a broken envelope, an unexempted
unknown type, and the exemption going stale all fire; the real fixture does
not.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: data-contracts)

Command (in the frontmatter, superseding the originally proposed
`scripts/validate_wire_fixtures.py`):

    .venv/bin/python $RULE_DIR/scripts/check_wire_fixtures.py   # for each tests/fixtures/*.json bearing an 'events' array: TypeAdapter(RunEventEnvelope).validate_python(entry) for every entry, resolve it to a concrete union member, exit 1 listing failures

Condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- 'tests/fixtures/' 'aii_lib/src/aii_lib/run/' | grep -q .`

Delete-check: The real deletion is generating fixtures FROM the producers (golden capture
from an emit run), which would make freshness structural — heavier machinery
than one fixture justifies today. The validation pin is the cheap end; if
producer-generated fixtures ever land, this rule collapses into the generator
and dies.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Live defect (5/12 fixture events fail the real TypeAdapter — parity
tests exercising a hand-typed dialect) and a silent failure mode: a stale
fixture makes both readers agree on shapes the journal cannot carry. Distinct
from pending rule-parity-fixture-two-readers (both-readers coverage) — this is
schema truth, that is reader coverage; the two compose.
- KEEP: Live defect executed during review (5/12 fixture events fail the real
TypeAdapter) — a parity test folding a hand-typed dialect is a green gate
checking nothing; check is one validate loop, distinct from parity-fixture-
two-readers (readers vs schema truth).
- KEEP: Executes the live TypeAdapter — genuinely non-vacuous (5/12 events
fail today). Distinct from pending rule-parity-fixture-two-readers (readership
vs wire-validity). Detection of 'wire-shaped' must be closed (top-level events
key) and assert >=1 fixture matched.

## History — the defect as proposed (2026-08-20) and its repair

As proposed: tests/fixtures/run_cost_parity.json failed this — 5 of its 12
events did not validate against RunEventEnvelope (verified with TypeAdapter:
every summary_cost event, the agent_summary at index 11 and the decoy at
index 10 omitted parent_id, which BaseMessage declares REQUIRED at
aii_lib/src/aii_lib/run/_messages/_base.py:47,91 and every real producer
stamps). The fixture was born stale: parent_id was already required at its
creating commit c509ff509. If either reducer ever keys on parent_id/path,
such a fixture exercises a branch real data never takes.

STATUS (2026-08-22): the defect this rule was proposed from is FIXED —
verified independently (TypeAdapter(RunEventEnvelope) over the fixture:
5 of 12 events invalid before, 0 after) and repaired by stamping
parent_id="orchestrator" on the five run-level messages, matching the
convention event 6 already used for a non-task emitter. Both readers
stayed green across the change, which is the point: parent_id is
structural, so a wire-true fixture reduces to the same totals. The rule
itself remains worth approving as the GUARD — nothing currently stops
the next fixture from being born stale the same way.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **premise holds, defect
already FIXED; stock is now zero.**

Re-ran the check this rule proposes: every one of the 12 events in
`tests/fixtures/run_cost_parity.json` validates through
`TypeAdapter(RunEventEnvelope)`. **0 of 12 fail**, against the stated 5.

The premise is not what changed. `parent_id` IS required — checked at the
model rather than in prose: `BaseMessage.model_fields["parent_id"]`
reports `is_required() == True` with no default, and `_base.py:47` says
"``parent_id`` is REQUIRED. Every message must declare its owning
[node]". What changed is the fixture: **0 of 12 events omit it now**, and
`0c9711c84` ("fix(tests): the cost-parity fixture is wire-true again",
2026-08-22) is the commit that repaired it, two days after `c509ff509`
created the fixture stale.

**That makes the rule stronger, not weaker.** It becomes a regression
guard over a class that demonstrably occurred once, with a named repair
commit as evidence rather than a hypothetical — and the original failure
mode is exactly the one worth guarding: two readers, a Python test and a
frontend twin, both fed a fixture that no real producer could emit, so
both agreed with each other about a shape the wire never carries.
