<!-- hook: metered-skill-spend-contract -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every skill script reading a paid provider key implements the spend-contract pair from aii_lib.run_cost — book via AII_COST_LEDGER, gate on AII_FREE_TOOLS — or sit on a pinned exemption table.

Every skill script that reads a paid provider key (OPENROUTER_API_KEY,
SERPER_API_KEY, RUNPOD_API_KEY) implements the spend-contract pair from
aii_lib.run_cost — books its dollars via a record_external_cost call under
AII_COST_LEDGER and gates its paid path on AII_FREE_TOOLS — or sits on a
pinned, per-file annotated exemption table; free-by-design skills gaining a
paid-key reference fail until classified.

**The gap that motivated this rule is CLOSED and the mechanism arrives GREEN**
(re-run 2026-08-28: rc=0). `aii_or_call_llms.py` gained both halves of the
contract in `bb4b459ea` ("OpenRouter LLM calls book their spend and honour
$0 runs") and now carries 6 AII_COST_LEDGER/AII_FREE_TOOLS references.
Census today: 6 skill scripts hold a paid provider key; 3 carry the full
contract (aii_or_call_llms.py, aii_fast_web_search.py, concept_fig_gen.py)
and 3 sit on the pinned exemption table with their reasons. The rule is a
pure regression guard over a closed set.

## History — the uncovered spend site as found (2026-08-26)

aii-openrouter-llms was the live uncovered spend site: .claude/skills/aii-
openrouter-llms/scripts/aii_or_call_llms.py:53,79 read OPENROUTER_API_KEY and
called any catalog model (paid included), returned only token counts (lines
296-298), and had zero references to AII_COST_LEDGER, AII_FREE_TOOLS, or
cost_usd (repo grep at the time: only aii-web-tools and aii-concept-fig-gen
wrote the ledger). Meanwhile
aii_pipeline/src/aii_pipeline/prompts/components/resources.py:20-21 makes
OpenRouter the ONLY sanctioned LLM route for experiment artifacts, authorizes
up to $max_usd per artifact, and offers the skill by name (line ~33);
aii_lib/src/aii_lib/run/events/run_budget.py:5-8 states that budget is
'enforced by nothing at all', and billed_usd_for_run can only count booked
cost events — so unbooked OpenRouter spend is invisible to BOTH the dashboard
run cost (external_tool_cost, run_cost.py:88-153) and the spend ceiling. The
contract pair is defined at aii_lib/src/aii_lib/run_cost.py:42-58 ('one says
where to report spend, the other whether spending is allowed'), and the two
compliant skills show the shape (aii_fast_web_search.py:405,577-588;
concept_fig_gen.py:492,1070-1080). aii_runpod_gen_pod.py prints cost_per_hr
(lines 221-233) and books nothing — the exemption table classifies runpod
scripts as infra-not-run-spend explicitly instead of silently.

Mechanism (implemented 2026-08-26, `scripts/check_metered_skill_contract.py`
plus its pinned `scripts/spend_classification.yaml`):

    .venv/bin/python $RULE_DIR/scripts/check_metered_skill_contract.py

**It arrived RED on exactly one file, and that one was real.** Measured
then: 6 skill scripts held a paid provider key (a 7th match is a rule-engine checker
that merely NAMES the variables — the `.claude/skills/*/scripts/*.py` glob
reaches into `amg-hooks` itself, so the rules tree is excluded). Two
carried the full contract. Three cannot spend and are pinned with the reason:
`aii_or_get_llm_params.py` and `aii_or_search_llms.py` call only
`openrouter.ai/api/v1/models`, the free catalog, and
`aii_runpod_gen_template.py` makes no HTTP call at all. That left
`aii_or_call_llms.py`, which reaches `/api/v1/responses` — inference on any
catalog model — with neither half of the contract; `bb4b459ea` closed it.

**The gate is the CONTRACT, not an endpoint list, and getting that backwards
fails open.** An earlier version gated on a list of billing paths and reported
both COMPLIANT skills as unclassified gaps, because they bill through paths
nobody had enumerated (`/api/v1/images`, `api.exa.ai`, HF inference). A list
of billing paths cannot be kept complete, and a check that needs it to be
complete fails open the day it is not. Booking spend is itself the evidence
that a script can spend, so a script carrying both halves is compliant
whatever it calls; the endpoint list survives only to name the billing path in
a finding.

Closing the one gap was not a code tidy. Adding the gate means a paid call
can newly be REFUSED when `AII_FREE_TOOLS` is set, which changes what a
running pipeline does — and this is the route
`prompts/components/resources.py` makes the ONLY sanctioned one for
experiment artifacts, with a per-artifact dollar budget. That behaviour
change landed with `bb4b459ea`; what remains for the owner is approving the
guard that keeps the set closed.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: observability-cost)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    $RULE_DIR/scripts/check_metered_skill_contract.py  # scans .claude/skills/*/scripts/*.py for paid-key env reads; each hit must reference both AII_COST_LEDGER and AII_FREE_TOOLS (record_external_cost call present) or match the annotated exemption table in the script; exits 1 listing offenders

Proposed condition: `git diff --cached --name-only -- '.claude/skills/' 'aii_lib/src/aii_lib/run_cost.py' | grep -q . || exit 1  # plus always-run in all-mode`

Delete-check: The dimension cannot be deleted by withholding the key: resources.py:20 makes
OpenRouter the sole sanctioned experiment-LLM route, so the spend site is
product-intended. The deletion-shaped alternative — dropping the per-provider
ledger entirely and trusting agent self-restraint — is exactly what
run_budget.py's module docstring documents as the failure that shipped
('$1000, 18h' with no ceiling). Enforcing booking coverage is the surviving
option; the exemption table keeps the pinned set minimal so covered-by-default
is the end-state.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Live uncovered spend site (aii-openrouter-llms reads
OPENROUTER_API_KEY, books nothing, ignores AII_FREE_TOOLS) and tonight's
incident proved unmetered skill spend is real money. Closed-world coverage of
the spend contract across skills is distinct from rule-cost-accounting
(derivation parity among writers that DO book) and rule-free-first-external-
services (provider ordering). High value, …
- KEEP: Live uncovered spend site (aii-openrouter-llms reads the paid key with
zero ledger/free-tools references) in the exact class tonight's concept-fig
incident proved real; closed-world classification of paid-key readers is the
right shape. Absorbs ledger-writer-helper-parity.
- KEEP: Tonight's incident class, with aii-openrouter-llms as a live uncovered
spend site; paid-key-name grep over skill scripts requiring the
AII_COST_LEDGER/AII_FREE_TOOLS pair or an annotated exemption is closed-world
(keyed on the key names themselves) and loud. Complements behavioral rule-
free-first-external-services, doesn't duplicate it.
