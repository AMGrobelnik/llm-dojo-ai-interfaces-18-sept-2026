# A new pipeline module joins every place that already names all of its siblings

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 2s | active |

## Why

Adding a step module means touching a scattered set of registries: frontend
display maps, a Python workflow table, a prompt directory. Miss one and
nothing fails — the run renders a permanently-pending row, or the module
never executes. The rule asked a committing agent to hand-check roughly 28
sites whenever a module landed under `steps/`, and the condition fires only
on an ADDED file there, so it ran nine times in the ledger with no recorded
evidence text to reproduce.

The open-ended "check the 28 sites" reduces to a closed rule the tree itself
supplies: **a place that names every one of a module's siblings is a
checklist, and the module must join it.**

## Mechanism

Registries are found, never listed. No registration path appears anywhere in
the checker; the only project knob is `CONFIG["module_roots"]`.

| failure mode | mechanism |
|---|---|
| missing from a frontend map | bracket-span scan over TS/TSX/JSON |
| missing from a Python registry | `ast` collection-literal spans |
| no prompt directory | path mirror: a dir naming every sibling |
| in one map, not the next | spans are per-literal, not per-file |
| named only in a comment | comments and docstrings blanked first |

Requiring EVERY sibling is what keeps a partial grouping — a two-of-five set
such as `NON_LLM_MODULES` — from demanding membership. A group with fewer
than two other modules is skipped and reported as skipped: one sibling is not
a checklist.

Some modules cannot appear as a single token in a per-module registry even
though a checklist names every one of their siblings — a module that fans out
into several differently-named per-artifact rows, or one that runs no agent
at all, so the agent/model registries correctly never mention it. That is a
different shape from a partial grouping (the checklist here names every
OTHER sibling, just not this one), so `sibling_coverage` cannot absorb it.
`CONFIG["module_registry_exempt"]` is the declared opt-out: exactly the
`(group, module)` pairs known to be like this, each with a required one-line
reason. An exempt module is dropped from the modules checked for their OWN
registration; it still counts as a sibling when a different module in its
group is checked, so a real gap in that group is still caught.

A different shape again is a module that IS registered everywhere its
siblings are, just under a spelling its own filename does not derive.
`gen_viz` (`aii_pipeline/.../_4_gen_paper_repo/_2_gen_viz.py`) is spelled
`viz_gen` at every run-config site — the canonical keys in
`aii_config/frontend/config.yaml`, the server schema's
`viz_gen_image_model: Literal["flash","pro"]`
(`aii_server/dashboard/api/run_config/_schemas.py:190`), and the module's own
`config.gen_paper_repo.viz_gen.image_model` read
(`_2_gen_viz.py:193,324`). Exempting it would be wrong: it has exactly one
registry entry, so its registration should still be checked, just under the
spelling it actually uses. `CONFIG["module_aliases"]` is the complementary
opt-in for this: a `(group, base)` key (read exactly like
`module_registry_exempt`'s) mapped to a non-empty list of the alternate
spellings a registry might use.

Aliases are **target-only**: an entry only ever ADDS a spelling that
satisfies a module's OWN registration (the collection-literal target
position, the path-mirror "already present" check, and the universe scan
that makes the alias text findable at all). It never widens SIBLING matching
or the `raw_seen` checklist gate, which stay on a module's canonical
file-derived tokens (`Module.tokens`) only, never `Module.target_tokens`.
This makes the knob monotone — a declared alias can only ever REMOVE a
finding, never introduce one. Without that restriction, a collection naming
a sibling only under its alias would start reading as a complete checklist
and begin demanding an unrelated, deliberately-absent module join it, which
is exactly the false-positive risk `module_registry_exempt` exists to avoid
in the first place.

Speed came from one measured change: a plain-substring prefilter ahead of the
boundary-anchored regex, 0.055 s against 1.718 s over the same file set. No
token can match the regex without matching as a substring, so the prefilter
is sound rather than a sampling shortcut.

## Stock

Measured against `/home/<user>/projects/research-monorepo` (worktree
`aii-75-hooks-precommit`), run read-only from that consumer tree:
**0 findings**, whole-tree sweep.

Before `CONFIG["module_aliases"]` existed, the same run reported **4
findings**, all the same one:
`aii_frontend/tests/unit/features-run-config/real-presets.fixture.json:7,231,467,685:
'gen_viz' is missing from a collection that names all 4 of its siblings in
aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo (deploy_gh,
gen_demo_art, gen_full_paper, gen_repo)`. Not drift: `gen_viz` IS registered
in every one of those collections, spelled `viz_gen` (see Mechanism above).
Adding the one `("_4_gen_paper_repo", "gen_viz"): ["viz_gen"]` alias entry
took the count to 0 without renaming anything in the consumer tree.

Before `CONFIG["module_registry_exempt"]` existed, the same run reported
**18 findings** — every one of them `gen_art` or `deploy_gh`, in the six
files where a checklist genuinely names all of the OTHER module's siblings
(`ai-models.tsx`, `ai-models.stories.tsx`, `real-presets.fixture.json` four
times over, and the two backend test enumerations
`test_a_preset_names_a_different_model_per_backend.py` and
`test_side_chat_yaml_path.py`). Both are structural, not drift: `gen_art`
fans out into five `execute_<type>` rows instead of appearing as one token,
and `deploy_gh` runs no agent, so it is correctly absent from every
agent/model registry. Neither can be fixed by renaming anything, which is
what distinguishes this from the naming-drift findings a prior stock
sweep found (and which were since fixed in the tree, not in the checker).

Because the hook is glob-scoped to `steps/*/*.py`, the stock bites only on a
commit that edits one of those three modules; a commit adding a new module,
which is what the rule exists for, is gated from day one. Re-run the no-arg
sweep once the naming is unified.

## Fragility

| refactor | effect | guard |
|---|---|---|
| `steps/` moves | 0 modules | exit 2, names CONFIG |
| the `_<N>_` prefix goes | 0 modules | same exit-2 path |
| a group shrinks to two | that group unchecked | deliberate floor |
| registries keyed by a union | nothing to police | delete the hook |
| a registry gets its own names | false positives | rename in the tree |
| a module can't be one registry token | false positives | `module_registry_exempt` |
| module spelled differently | false positives | `module_aliases` |

The fourth row is the rule body's own proposed end state: once every registry
is keyed by a closed union type, the compiler takes over and this hook can go.
The last two rows are the ONLY cases this hook opts a module in or out of by
name rather than by evidence in the tree — reviewed at PR time same as any
other config change, and the stock above shows exactly which findings each
one silences.

## Residue

Registrations that are neither a collection literal nor a path mirror — a
module wired by an `if/elif` chain, or by separate `from … import` lines in
different function bodies. A file-level co-occurrence variant was built and
measured first: it flags 13 findings in `_3_invention_loop` alone, so it was
dropped for precision. The workflow input/output models and the phase
`__init__` wiring named in the rule body go with it, for the same reason.

Also dropped: whether an omission is DELIBERATE. The rule allowed a pass when
the commit message said the registration lands in a following commit; no
program can read that, and no marker replaces it here.
