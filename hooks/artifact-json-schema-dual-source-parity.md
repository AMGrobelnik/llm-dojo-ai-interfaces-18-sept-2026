<!-- hook: artifact-json-schema-dual-source-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The aii-json skill's exp_*.json required keys equal aii_pipeline's out_schema.py verifier key sets, every schema file compiles as a JSON Schema, and every tracked .json in the skill dir parses

In full: the required-key lists in `.claude/skills/aii-json/schemas/exp_*.json`
(what the agent validates its output against mid-run) equal the `*_SCHEMA`
required-key sets in aii_pipeline's `_3_gen_art/*/out_schema.py` verifiers
(what the retry gate enforces) — and every schema file parses and compiles
as a JSON Schema, plus every tracked .json in the skill dir parses at all.

Dual-source verified in the tree: dataset/out_schema.py:86-87 pins
dataset_entry_required_keys=[dataset,examples] /
example_required_keys=[input,output], which currently equals
exp_sel_data_out.json's nested required lists exactly (checked by walking the
schema); experiment/out_schema.py:81-82 and evaluation/out_schema.py:82-83
repeat the pattern for their schemas. Prompts route agents to the skill schema
by NAME (dataset/u_prompt.py:67,93: 'validate full_data_out.json against
exp_sel_data_out.json schema (aii-json skill)') while
executors/artifact_validation.py routes the pipeline gate through the Python
verifier — a one-sided edit makes the agent pass its own validation and then
retry-loop against the gate (or ship data the gate never checked), burning
paid agent turns with no error naming the drift; tonight's incident class
(concept-fig tests silently buying live API images) shows exactly how agent-
loop money leaks go unnoticed. The dir is otherwise gate-free: rule-check-json
excludes .claude/skills wholesale as 'vendored', yet these four schemas are
first-party contracts the pipeline gates on — and the adjacent tracked
.claude/skills/aii-json/preview_data_out.json is a 0-byte file referenced by
nothing, live proof the dir escapes every existing check.

Mechanism (implemented 2026-08-26, `check_schema_parity.py`):

    .venv/bin/python $RULE_DIR/check_schema_parity.py

Arrives green: 4 paired contracts, 8 verifier key-lists all present in their
schemas, 4 schema files that parse and compile, 4 tracked JSON files in the
skill directory that parse.

**Every read is of the INDEX, and that was a fix, not a starting point.** The
checker enumerated through git and then opened the WORKING TREE
(`Path.read_text`), which is two snapshots wearing one name. Measured
2026-09-14 in a clone of the consumer, wired exactly as `lefthook.yml` runs it,
it failed in both directions: a required-key mismatch STAGED into
`exp_sel_data_out.json` and then reverted on disk exited **0**, so the commit
would have landed carrying the disagreement; the same mismatch left purely
UNSTAGED, with an unrelated file staged, exited **1** and blocked a commit that
did not contain it. Several agents share this checkout, so the second is
somebody else's half-finished edit deciding your verdict. `_index_text` is now
the one read — `amg-hooks-ls-files -s` for the listing (so `.amg-hooks-exclude` still
subtracts) and `git cat-file --batch` for the blobs, two processes whatever the
population — and it is the same helper `config-models-closed-schema` carries for
the same reason. A cannot-run now exits **2** rather than 1, matching the
`cannot run:` legend the rest of the tree uses.

`test_the_parity_verdict_reads_the_index_not_the_working_tree.py` pins both
directions plus the renamed-tree cannot-run.

**The pairing is DERIVED from the prompts, not declared in a manifest.**
Nothing maps `dataset` to `exp_sel_data_out`, and no naming convention would
let it be guessed. The prompt that creates the obligation also carries the
pairing — "validate … against exp_sel_data_out.json schema (aii-json skill)" —
so it is read out of the same text rather than kept in step by hand.

**The name appears both WITH and WITHOUT the `.json` suffix, and matching only
the suffixed form silently drops a pair.** `proof/u_prompt.py` says "Read the
exp_proof_out schema from the aii-json skill" — no extension, four times. A
first pass required `\.json`, found 3 of 4, and reported `proof` as a verifier
with no schema. It has both.

`research` has NEITHER side, which is consistent rather than a gap — its
artifacts are not JSON contracts. A kind with exactly ONE side is reported,
because that is what a one-sided edit leaves behind.

Comparison is by SET, not by position: the verifier lists required keys per
level while the schema nests them, so every verifier list must appear
somewhere as a `required` list rather than being matched structurally. That is
the property a one-sided edit breaks, and it ties the check to no single
schema's shape.

Probed eight ways: a verifier key absent from the schema, a verifier with no
named schema, a prompt naming an absent file, a schema that does not parse,
and one that parses but is not a valid JSON Schema all fire; a matching pair,
a neither-side kind, and the bare-name form do not.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: data-contracts)

Superseded proposal (the mechanism above ships it):

    .venv/bin/python $RULE_DIR/check_schema_parity.py  # for each artifact type: load exp_*.json, walk nested 'required' lists, import the matching out_schema module's *_SCHEMA dict + grep its top-level "Missing required 'X' key" literals, assert equality; Draft202012Validator.check_schema each file; json.loads every tracked .json under .claude/skills/aii-json/

Proposed condition: `git diff --cached --name-only -- '.claude/skills/aii-json/' 'aii_pipeline/src/aii_pipeline/prompts/steps/_3_invention_loop/_3_gen_art/' | grep -q .`

Delete-check: The real delete is collapsing the dual source: generate the skill's JSON
Schemas from the Python verifiers (or replace the Python required-key checks
with jsonschema validation against the skill files). Until someone does that
collapse, parity is the guard; the rule should be retired into the derivation
the day one side becomes generated.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Genuine two-language seam (agent-side JSON Schemas vs pipeline retry-
gate verifiers) no claimed rule spans — rule-artifact-schema-contracts covers
LLM-field exposure, not skill-schema parity. Drift here silently makes the
agent validate against a contract the gate won't accept. Keep; record the
generate-from-Python collapse as the eventual delete.
- KEEP: Genuine dual-source seam (skill JSON Schemas vs pipeline out_schema
verifiers) not covered by enforced rule-artifact-schema-contracts, which pins
the struct-out/prompt side; parity walk is cheap and a drift silently splits
what the agent validates from what the gate enforces.
- KEEP: Two independent definitions of the same contract with no gate is a
real seam; parse-both-and-compare-required-sets is mechanizable and loud.
Distinct from enforced rule-artifact-schema-contracts (LLM-marked-fields seam,
not the skill-JSON/verifier seam).
