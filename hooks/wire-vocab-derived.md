# A hand-typed TS union is not a second copy of a declared vocabulary

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 2s | active |

## Why

The rule body named this program as its own promotion path: *"a script that
diffs TS unions against the generated client is the promotion path"*. It is
now written, and the tree has 22 places where it bites.

Two shapes. A frontend union that the generated client **already exports** is
a duplicate of a derived type, and importing it costs one line. A frontend
union that mirrors a Python `Literal[...]` or `StrEnum` the client does
**not** carry is the case the rule cares about: the schema is not
route-reachable, so the generator emits nothing and the vocabulary gets
retyped by hand on the other side of the wire.

## Mechanism

`check.py` parses the union out of each changed `.ts`/`.tsx` with a tolerant
tokenizer (comments blanked in place so line numbers stay real) and compares
value SETS, so member order, quote style and line breaks are all irrelevant.

| finding | what it is |
|---|---|
| A | the same set a `types.gen.ts` union already declares |
| B | the same set a Python `Literal`/`StrEnum` declares |

The related set resolves in two steps, neither of them a path list. The
generated client is every tracked file named `types.gen.ts`, minus the ones
nested under another (those are the generator's own runtime subpackages,
carrying library vocabulary rather than wire vocabulary). The owning Python
declaration is found by grepping for the changed file's own union VALUES and
`ast`-parsing only the files that match — so a commit touching one `.tsx`
never reads the frontend tree and opens a handful of `.py` files.

**Both sides are read from the git INDEX**, and that is a change from the
converter's working-tree design. Reading TS from disk while grepping
`--cached`, or the reverse, judges two snapshots against each other: the
converter measured one such mismatch as a detector miss when it was a
snapshot mismatch. One snapshot for both sides removes the class, and it is
the snapshot the commit contains, so a peer's unstaged edit cannot create or
silence a finding here.

## Stock

Whole tree, at HEAD: **22 findings** (14 A + 8 B), 1.46 s. One changed `.tsx`
costs 0.03 s, which is what the hook pays.

| where | n |
|---|---|
| `tests/e2e/helpers/mock-run.ts` | 7 |
| `lib/types/backend.ts` | 4 |
| `run-config/types.ts` | 3 |
| `ai-models.tsx` | 2 |
| one each, six other modules | 6 |

Every line is a second copy of a vocabulary that exists elsewhere, so the
list is debt rather than noise: the A findings are a one-line import each,
and the B findings need the `Literal` moved onto a route-reachable schema
before the client can carry it. `backend.ts:28` is the purest case — its set
is declared twice on the Python side, once as a `Literal` and once as
`StrEnum PlanType`.

Injection measured 15/15 generated vocabularies and 22/22 Python-only ones
caught, with 0 false positives on three invented value sets that exist
nowhere — a detector firing on those would be matching shape, not relation.

## Fragility

| refactor | effect and guard |
|---|---|
| the generator renames its output | CONFIG knob; exit 2 if absent |
| the client stops emitting unions | exit 2, index is empty |
| the frontend moves | `--ts-pathspec`; exit 2 if empty |
| the tokenizer misreads some TS | a miss is a false negative |
| the checker goes inert | the stock test pins the debt list |

Three of the five are exit 2. The stock test asserts the recorded debt is not
EXCEEDED rather than matched exactly, so deleting one of the 22 duplicates —
the fix this hook asks for — does not fail the suite that guards it.

## Residue

Two vocabularies can coincide by accident (`"low"|"high"` as a priority and
as a resolution); the checker reports the pair and a person decides.
`MIN_MEMBERS: 2` is the only mitigation, and raising it would drop real
two-member wire vocabularies, of which the stock list holds two.

A TS union that is a strict SUBSET of a generated one is a deliberate
narrowing and passes; detecting it needs the intent. Choosing WHICH schema a
`Literal` should move onto is design work the checker names but cannot do.
Numeric unions and `as const` arrays used as vocabularies are out of scope.
