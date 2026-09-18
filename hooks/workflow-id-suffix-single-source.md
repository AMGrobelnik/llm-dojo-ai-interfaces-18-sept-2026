<!-- hook: workflow-id-suffix-single-source -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Workflow-id suffix grammar (-phase-/-iter-/-mod-/-retry-/-rerun-) is constructed only inside *_workflow_id helper functions

Every suffix has a named helper today (phase_workflow_id _phases.py:287, iter
ids _hypo_loop_iter.py:228 + _invention_loop_iter.py:550, mod ids
_invention_loop_modules.py:653 + _hypo_loop_modules.py:124/129 +
_gen_paper_repo_modules.py:511, retry stamping _invention_loop_modules.py:340)
EXCEPT `-rerun-`, which is inlined byte-identically in FOUR files:
_2_gen_plan.py:298, _3_gen_art.py:504, _2_gen_viz.py:477,
_3_gen_demo_art.py:468 (`f"{base_id}-rerun-{_rerun_seq[0]}"`). The grammar is
parsed downstream — aii_server/dashboard/services/run_lineage.py:62 splits on
'-phase-', run_events.py:163-165 enumerates the full grammar — so a drifting
copy is the exact twin-drift class behind d66fb8614 (hash-suffix width) and
69279ba42 (task-slug disagreement).

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: python-pipeline)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_id_suffix_sites.py  # AST: f-strings/concats containing the suffix tokens outside functions named *_workflow_id

**Construction, not mention** — the distinction that makes this an AST check
rather than a grep. A bare `"-phase-"` handed to `.split()` is a READ of the
grammar, and `run_lineage.py` and `run_events.py` are full of them; flagging
those would put every consumer in the report and bury the one producer that
matters. Only an f-string or a `+` concatenation embedding a token counts.

ADOPTION (2026-08-25): both defects this rule names are FIXED, so the gate
arrives green rather than red.

- `-rerun-` was inlined byte-identically in four step modules across two step
  families. It now has `rerun_workflow_id` in the new `workflows/_ids.py`,
  placed there rather than beside a caller because both `_3_invention_loop`
  and `_4_gen_paper_repo` apply it.
- The gate then found a second, subtler one the proposal had recorded as
  compliant: `_module_wf_id` mints `-mod-` and is genuinely the single source
  for it — six public `*_module_workflow_id` helpers wrap it — but its NAME
  did not match the convention this rule states. Renamed to
  `_module_workflow_id`, 7 occurrences, private to its module, so the rule is
  now literally true rather than true-with-an-exception. That is the gate
  earning its place before it was even approved.

Proven to bite in a throwaway tree: an f-string minting `-mod-` and a `+`
concat building `-iter-`, both outside a helper, are named; a `*_workflow_id`
helper doing the same and a `.split("-phase-")` read stay silent.

Proposed condition: `[ "$RULES_MODE" = all ] || git diff --cached --name-only -- aii_pipeline | grep -q .`

Delete-check: Yes — the four inline `-rerun-` sites collapse into one
`rerun_workflow_id(base_id, seq)` helper beside the other 19 helpers; the rule
enforces that deleted end-state rather than policing copies. Full deletion
(grammar as shared constants importable by aii_server) is the eventual
aii/seam move; this rule is the pipeline-side half.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Delete-first: add rerun_workflow_id beside the 19 existing helpers,
kill the four inline -rerun- sites, then enforce that suffix grammar lives
only in *_workflow_id helpers.
- KEEP: 19 helpers already exist; only -rerun- is inline. Collapse the
stragglers into one helper then grep for inline suffix literals — id grammar
is parsed elsewhere, so drift is a real cross-reader hazard. Cheap.
- KEEP: Grep for the five suffix literals outside *_workflow_id helper
functions, after collapsing the four inline -rerun- sites. Literal-ban shape,
fails loudly.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **the claim the rule rests
on is exact. Two stated numbers are not.**

The load-bearing claim is "every suffix has a named helper; only `-rerun-` is
inline". Tested by sweeping the whole tree for an f-string that builds a
dashed id suffix, rather than by checking the sites the body already names:

    git grep -nE 'f"\{[a-z_]*(id|_id)\}-[a-z]+-\{' -- '*.py'

Fifteen hits. Eleven are inside `run/workflows/` — the helper modules — and
one of those is a docstring quoting the pattern. The remaining **four are the
`-rerun-` sites, in exactly the four step modules named**, with no fifth
anywhere. So the asymmetry is real and completely enumerated: `-phase-`,
`-iter-`, `-mod-`, `-task-` and `-retry-` are each behind a helper, and
`-rerun-` alone is written by hand.

**Line references: 13 of 14 exact.** `_3_gen_demo_art.py` carries the rerun
construction at **468**, not 464; line 464 is the `base_id = ...` assignment
two statements above it. Corrected in the body above. Every other reference
lands on the exact statement claimed, including the downstream parsers
(`run_lineage.py:62` splitting on `-phase-`, `run_events.py:163` opening the
grammar comment).

**"19 helpers" matches no scope I can construct.** Counting `def
\w*workflow_id(`:

| scope | count |
|---|---|
| `aii_pipeline` only | 18 |
| `aii_server` only | 2 |
| both | 20 |

19 is neither. Checked whether today's work explained it — it does not; both
server helpers predate this proposal (`0572af108` 2026-05-09 and `8ab669149`
2026-08-22). The likeliest reading is an off-by-one against the pipeline set,
which is the set the rule actually concerns.

This does not weaken the proposal. Its delete-first move is "add
`rerun_workflow_id` beside the existing helpers", and whether there are 18 or
20 neighbours changes nothing about that. But the body should say **18
pipeline-side helpers**, since a reader who counts will get 18 or 20 and
neither will match.
