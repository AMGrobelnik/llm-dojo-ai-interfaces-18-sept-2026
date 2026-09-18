<!-- hook: prompt-figure-vocab-once -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# The figure vocabulary (aspect_ratio and figure_type Literal sets) is declared exactly once and imported everywhere else, never re-typed

LANDED 2026-09-03 — the hoist below is done and this rule now enforces its
end-state with ``check.sh`` rather than proposing it. ``FigureType`` and
``AspectRatio`` are declared once, in
``_4_gen_paper_repo/_2_gen_viz/out_schema.py:35-36``, and
``_3_invention_loop/_4_gen_paper_text/out_schema.py`` imports both alongside
the ``Figure`` it already imported. The wire is provably unchanged: the
combined ``model_json_schema()`` of ``FigureSpec`` and ``PaperText`` is
byte-identical across the swap (8259 bytes both sides), which is the check
that matters — these Literals become the model's allowed output values.
Prompt PROSE in ``u_prompt.py`` still names the same values as guidance; that
is not a second declaration of the set, and the gate deliberately counts only
``Literal`` declarations.

The original finding, kept because it is the reasoning:

The identical 7-value aspect_ratio Literal is hand-typed twice:
_3_invention_loop/_4_gen_paper_text/out_schema.py:71-72 (FigureSpec) and
_4_gen_paper_repo/_2_gen_viz/out_schema.py:61-62 (Figure); figure_type
Literal[\"data\",\"concept\"] likewise at :42 and :38. paper_text already
imports gen_viz's Figure (out_schema.py:16) for to_figure() (:87), so a
shared type alias costs one import. History shows this exact seam drifting: c0bf9e189
'five seams between paper text, gen_viz and gen_full_paper' and 563c891f4
'stale chart-type menu'. rule-viz-figure-pipeline's test_viz_seams.py pins the
CURRENT sets behave compatibly (test at line 62 compares menus) — this rule
instead removes the dimension so a future value added to one twin cannot
exist.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: prompts)

Proposed command (implemented at approval):

    test "$(grep -rcE 'Literal\[\"1:1\"|Literal\[\"data\", \"concept\"\]' aii_pipeline/src/aii_pipeline/prompts --include='*.py' | awk -F: '{s+=$2} END{print s}')" -le 2

Delete-check: The deletion IS the proposal: hoist AspectRatio/FigureType aliases into one
module (gen_viz out_schema or a shared vocab module), repoint FigureSpec, then
the count-based gate enforces the deleted end-state. Behavior parity of the
seam remains rule-viz-figure-pipeline's job — no overlap.

Filter verdicts (3-lens adversarial, kept 2/3):
- KILL: Same class as the artifact-type proposal (pipeline vocabulary re-typed
instead of imported); after the hoist, one pipeline-vocab-single-source rule
pins both. Not covered by wire-vocab-derived, which is strictly the TS seam.
[merge->rule-artifact-type-vocab-derived]
- KEEP: Identical 7-value Literal hand-typed twice across schemas that must
agree (figures flow between the two steps). Hoist once, grep the deleted end-
state; concrete cmd instance of wire-vocab-derived, cheaper than agent
verification.
- KEEP: Hoist the aliases once, then grep bans the re-typed Literal value
sets. Literal-ban shape, deterministic.

Note on the KILL pointer: no rule named rule-artifact-type-vocab-derived
exists anywhere under rules/ or rules-pending/ — the merge target never
landed, and the nearest analogue, rule-artifact-type-vocab-agrees, has
been retired from the corpus — so the merge was not applied and this rule
stays a standalone vocabulary-is-closed member per its 2/3 KEEP.
