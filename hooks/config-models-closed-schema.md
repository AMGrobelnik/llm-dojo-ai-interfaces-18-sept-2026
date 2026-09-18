<!-- hook: config-models-closed-schema -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every pydantic model bound to aii_config yaml (config_models/, pipeline_config.py, run/config.py) declares extra="forbid" — no config model silently ignores unknown keys

The convention is 100% uniform today (verified: 15/15 classes in
config_models/infra.py, 14/14 in invention_loop.py, 8/8 in gen_paper.py, 4/4
in run/config.py declare it) but nothing pins it. The whole lenient-on-
unknown/strict-on-invalid policy (pipeline_config.py:375-419) works ONLY
because extra_forbidden errors fire; one new model without forbid means a
typo'd yaml key validates silently and the setting never takes effect —
exactly the failure the bootstrap test calls 'dropped at load, once per load,
forever' (rule-server-account-
bootstrap/test_new_user_bootstrap_config.py:110-131).
claude_cred_manager/src/claude_cred_manager/config.py models are exempt by documented decision (its
loader deliberately tolerates leftover legacy keys, config.py:139-141).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: config-yaml)

Command (checker implemented 2026-08-28):

    .venv/bin/python $RULE_DIR/scripts/check_config_models_forbid.py

Scoped exactly as the verification advised: the `config_models/` package plus
`pipeline_config.py` and `run/config.py` (and its future `_config/` parts),
enumerated through git — all under `aii_pipeline/src/aii_pipeline/`. An early
draft pointed the scope at `aii_lib/src/aii_lib/run/config.py`, which does not
exist, so the 4 `run/config.py` models silently dropped out of the population
while a floor of 30 still passed on 38; repointed 2026-08-28 and the floor
raised to 40. AST-walked, with inheritance honoured — a model that gets
`extra="forbid"` from a parent in the population counts as closed. Measured
after the repoint: **42 models, all closed** (checker exit 0); a mutation
opening one is reported by file, line and name.

Condition (implemented): `[ "$RULES_MODE" = all ] || git diff --cached
--name-only -- '<the config-model scope above>' | grep -q .` — all-mode RUNS
the checker (a whole-tree rule has to be measured whole-tree, and this one
finishes in well under a second), commit mode gates on the staged scope. An
earlier condition (`[ "$RULES_MODE" = commit ] || exit 1; …`) had the
polarity reversed and skipped all-mode outright; fixed 2026-08-28.

Delete-check: The dimension could be collapsed instead of policed: a shared
ConfigBase(BaseModel) with model_config = ConfigDict(extra="forbid") that
every config model inherits — then the rule checks 'inherits ConfigBase',
which is the cleaner end-state and the same AST scan. Either form needs the
rule; pure deletion is impossible (pydantic has no per-package default).

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Winner over rule-config-models-forbid-extra (broader scope, includes
run/config.py). 100% uniform today and the whole lenient/strict overlay policy
silently breaks if one model omits it; adopt the shared ConfigBase collapse
and enforce inheritance.
- KEEP: Canonical of the extra=forbid pair (absorbs rule-config-models-forbid-
extra). 100% uniform today and the documented lenient/strict policy silently
collapses if one model omits it. Best form: shared ForbidBase + inheritance
check; either way a cheap AST scan.
- KEEP: Survivor absorbing rule-config-models-forbid-extra: AST over the
config-model modules asserting extra='forbid' (or ForbidBase inheritance per
its delete-check). 100% uniform today, unpinned; check is deterministic and
loud.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **every count and every line
reference is exact. The scope definition is the part that needs care.**

Counted with `ast` rather than grep:

| file | claim | measured |
|---|---|---|
| `config_models/infra.py` | 15/15 | 15/15 |
| `config_models/invention_loop.py` | 14/14 | 14/14 |
| `config_models/gen_paper.py` | 8/8 | 8/8 |
| `run/config.py` | 4/4 | 4/4 |

The three `config_models/` figures sum to 37, and the package holds exactly
**37 models with 0 missing** `extra="forbid"` — so the named files are not a
sample, they are the whole package. With `run/config.py` that is **41 of 41**,
and "100% uniform today" is confirmed rather than taken on trust.

All three line references land on what they claim.
`pipeline_config.py:375` opens `_validate_pruning_unknown`, whose docstring
reads "Lenient-on-unknown / strict-on-invalid — the single validation policy",
and 419 is that method's last line. The bootstrap test at :110 opens "The
consequential one, and the reason a successful load is not enough". And
`claude_cred_manager/src/claude_cred_manager/config.py:139-141` is the comment recording that a
leftover `redact_credentials` key is ignored on load — the documented
exemption, exactly as described.

**The warning for whoever builds the check.** A whole-tree sweep for
`BaseModel` without `extra="forbid"` returns **52 of 97** first-party models.
Only 6 of those 52 are the documented exemption; the other ~46 are not config
models at all — workflow payloads (`_gen_paper_repo_modules.py`,
`_invention_loop_modules.py`), prompt output schemas (`out_schema.py`,
`schema_code.py`), message bases and artifacts. Several of those SHOULD stay
open, since a wire model that forbids unknown keys breaks on the first
forward-compatible field.

So the population is "models that back a YAML config file", not "models". Get
that wrong and the rule ships with 52 findings, 46 of them wrong, on a
convention that is currently perfect. Anchoring on the `config_models/`
package plus an explicit list of the other config-backed modules is the
cheapest correct scope.
