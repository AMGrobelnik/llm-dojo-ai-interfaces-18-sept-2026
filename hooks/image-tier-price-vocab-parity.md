<!-- hook: image-tier-price-vocab-parity -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The paid image-tier vocabulary agrees across its repo seam

The paid image-tier vocabulary agrees across its repo seam: the pipeline
config Literal for gen_paper viz `image_model` equals `MODEL_TIERS`' keys in
concept_fig_gen.py, and every `MODEL_TIERS` slug is priced in BOTH fallback
tables (`_IMAGE_OUTPUT_PRICE_USD` and `_INPUT_IMAGE_PRICE_USD`) — no
configurable tier can resolve to an unknown or unpriced model.

dfd1fd3b5 ('config-driven viz image model') + 92958849e put this vocabulary on
two sides of a seam with no check:
aii_pipeline/src/aii_pipeline/utils/config_models/gen_paper.py:71 declares
Literal["flash","pro"]; _2_gen_viz.py:191 threads it into the prompt;
prompts/steps/_4_gen_paper_repo/_2_gen_viz/u_prompt.py:106 orders the agent to
pass '--model {image_model}' on EVERY generation call. On the skill side,
concept_fig_gen.py:413 defines MODEL_TIERS={"pro","flash"}; :967 pins the
`--model` flag to choices=["pro","flash"], so a tier the config offers but the
skill lacks exits 2 with 'invalid choice' on the prompt path — loud, and far
from the config that caused it, but not silent (measured; the raw-id
pass-through in _resolve_model at :416-420 is reachable only by importing the
function directly). What IS silent is the price half: :485 prices any model
absent from the tables from the PRO table — the fallback estimate used whenever
a response carries no usage block, per the comment at :464-469 — so an
unpriced slug misprices those ledger rows with a plausible-looking number.
Not covered by rule-viz-figure-pipeline (spec routing), rule-
free-first-external-services (failover behavior), or rule-config-models-
closed-schema (schema closedness) — this is cross-seam value-set parity plus
billing-table completeness.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: observability-cost)

Proposed command (implemented at approval):

    scripts/check_image_tier_vocab.py  # ast-parses the image_model Literal from config_models/gen_paper.py and MODEL_TIERS/_IMAGE_OUTPUT_PRICE_USD/_INPUT_IMAGE_PRICE_USD from concept_fig_gen.py; asserts set equality of tiers and that every tier's slug keys both price tables

Proposed condition: `git diff --cached --name-only -- 'aii_pipeline/src/aii_pipeline/utils/config_models/gen_paper.py' '.claude/skills/aii-concept-fig-gen/' | grep -q . || exit 1`


## IMPLEMENTED 2026-08-26 — `scripts/check_image_tier_parity.py`

    .venv/bin/python $RULE_DIR/scripts/check_image_tier_parity.py

Arrives green: 2 tiers, config Literal and `MODEL_TIERS` agree, and both tier
models appear in both price tables.

**What earns the gate is a three-way hand-maintained vocabulary plus a silent
price fallback — not two silent failures, which is what the proposal claimed
and the 2026-08-22 verification below corrected.** {flash, pro} is spelled in
three places nothing ties together: the config Literal (gen_paper.py:71),
`MODEL_TIERS` (concept_fig_gen.py:413) and the argparse `choices` list (:967).
A tier the config offers but the skill lacks fails LOUD — the prompt always
passes `--model`, and argparse exits 2 with 'invalid choice' — but every viz
call in the run fails that way, far from the config line that caused it. The
check pins the first two copies against each other; the `choices` list is not
compared today, so a tier added to both the Literal and `MODEL_TIERS` but not
to `choices` still fails loudly at argparse. The silent half is pricing: a
tier model absent from the price tables is charged from the PRO table by
`.get(model, _IMAGE_OUTPUT_PRICE_USD[MODEL])` whenever a response carries no
usage block, so a cheaper tier bills the fallback estimate at the dearer rate
and the only symptom is a plausible-looking number.

**The two sides are keyed differently, and conflating them is the easy
mistake.** `MODEL_TIERS` maps TIER NAME to MODEL ID; both price tables are
keyed by MODEL ID. So the config Literal is compared against the tier KEYS and
the price tables against the tier VALUES.

Values are matched by NAME (`MODEL`, `FALLBACK_MODEL`) rather than resolved
string, so the check is exact without evaluating what those constants hold.

Probed five ways: a config tier the skill lacks, a skill tier the config lacks,
and a tier model missing from either price table all fire; the real pair does
not. One probe initially reported a miss because its string mutation did not
apply — re-done with a regex that provably removed the key, it fires.

Delete-check: Deleting the tier indirection (raw slugs in config) would still leave the
price-table membership half needed and would surrender the closed Literal the
run-config UI enumerates; deleting the fallback tables would leave usage-less
200 responses unpriced (concept_fig_gen.py:464-469 documents why the table
exists). Neither end deletes cleanly, so the parity is enforced.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Fresh seam (dfd1fd3b5/92958849e) crossing config Literal -> prompt ->
subprocess-isolated skill where no import can enforce agreement, and the
failure (unknown or unpriced tier) is silent cost-accounting corruption. The
claimed vocab rules (wire-vocab-derived, event-vocabulary-parity, prompt-
figure-vocab-once) each own different vocabularies; none spans this config-to-
skill seam. Keep.
- KEEP: Fresh seam from dfd1fd3b5/92958849e with three hand-agreeing
vocabularies (config Literal, MODEL_TIERS, two price tables) and no check; a
mismatch means an unpriced or unknown tier chosen from config. Cheap set-
compare.
- KEEP: Fresh seam from dfd1fd3b5 (config Literal on one side, MODEL_TIERS +
two price tables on the other, no gate); AST-parse both sides and compare sets
— no imports needed, loud on any unpriced or unknown tier.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
Pipeline-side refs are exact: `grep -n image_model` gives gen_paper.py:71
`image_model: Literal["flash", "pro"] = "flash"`; _2_gen_viz.py:191
`image_model = config.gen_paper_repo.viz_gen.image_model if config else
"flash"`; u_prompt.py:106 `ALWAYS pass \`--model {image_model} --style
neurips\` to EVERY concept_fig_gen.py call` (also :111, :116). Skill-side refs
are off by one: MODEL_TIERS is at :4

Corrected statement of fact:
The seam exists but the failure mode does not. Corrected: the config Literal
(gen_paper.py:71) and the skill are already tied on the path the prompt
actually uses -- concept_fig_gen.py:961 pins `--model` to
`choices=["pro","flash"]`, so an unrecognised tier exits 2 with 'invalid
choice' rather than being forwarded as a raw model id (measured).
_resolve_model's raw-id pass-through (:420) is documented behaviour reachable
only via direct import, and the PRO-table price fallback (:485) is an
explicitly-declared estimate used only when a response carries no usage block,
with OpenRouter's usage.cost as the source of truth (:463-465). The residual,
much smaller, gap is that the argparse choices list is a THIRD hand-maintained
copy of {flash,pro} alongside the config Literal and MODEL_TIERS -- a three-
way vocabulary pin, with no silent-mispricing consequence.
