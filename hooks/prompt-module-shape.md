# A prompt module keeps the shape the prompt package is read through

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

The agent rule was applied 218 times and failed 30, and left **no auditable
evidence line** in any ledger snapshot — 218 applications, not one
trace. That
absence is itself the argument for a program: an invariant nobody can
audit after the fact is one nobody can tell was ever checked.

Its own delete-check had already asked for this: *"an AST gate could mechanize
~70% of this rule later (command upgrade, same rule id)"*. Twelve of its
clauses have a closed form; they are here, and the rest is documented below as
residue.

The rule is filed under `research-monorepo` rather than `general` because the shape
it pins is this repo's prompt package convention — `out_schema.py` with a
discriminating `kind`, `s_prompt`/`u_prompt` modules, banner order, and
components imported absolutely.

## Mechanism

`check.py` parses each in-scope module with `ast` and judges twelve
independent clauses. Every one is per-file: nothing walks the tree.

| # | clause |
|---|---|
| 1-3 | `kind` first, a plain default, matching its `Literal` |
| 4-5 | `Field()` keyword-only, `description=` last |
| 6 | `Annotated` marker order |
| 7 | s_/u_ module docstring opening |
| 8 | components imported absolutely |
| 9 | `# ===` banners in the pinned order |
| 10-11 | a template function has no docstring, one return |
| 12 | a component spliced as a call, not a bare name |

Module kind is matched by filename PREFIX, not by exact name: the tree holds
`s_prompt_code.py`, `u_prompt_site.py` and two more variants, and the exact
match an earlier draft used exempted all four in silence.

The judged text is the git INDEX copy, so a peer's unstaged edit to a prompt
module cannot fail a commit that does not contain it.

## Stock

Whole tree, at HEAD: **0 findings**, 0.08-0.09 s over 83 tracked modules under
a `prompts/` directory.

Zero here is a measured population rather than an inert checker. The construct
census lines up with the rule body's own: 35 `kind` fields, 201 `Field()`
calls, 165 `Annotated[...]` subscripts, 96 banners across 44 files, 32
s_/u_ modules, 26 template functions. Injection over the real modules scored
**192 of 192** across nine mutation shapes, every group represented.

## Fragility

| refactor | effect and guard |
|---|---|
| `prompts/` renamed | no-arg mode exits 2; one CONFIG key |
| `s_prompt.py` renamed | prefixes are CONFIG; census warns |
| `Field` aliased | goes quiet, not wrong; needs a CONFIG entry |
| the markers renamed | `MARKER_ORDER` is CONFIG; 165 sites |
| the population empties | exit 2, never 0 |

## Residue

"One public entry point" is deliberately not enforced: the rule body's own
re-measure finds 20 of 30 modules satisfying it and calls the other 10
extensions of the shape rather than violations, so a gate would manufacture 10
findings against a shape the text accepts.

"Components called, never pasted as text" is converted only in its closed
half, the bare-name interpolation. Detecting duplicated prose is a similarity
problem, not a predicate. Uppercase component CONSTANTS interpolated bare are
correct usage at 7 sites and are excluded by the same test.

Whether a docstring is a good summary, whether a helper deserves to exist, and
how a retry prompt should be worded all stay with the agent.
