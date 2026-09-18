# Agent dispatch goes through the one router, not around it

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 1s | active |

## Why

`exec_mode_router.py` is the single place that constructs an execution
environment and calls `run_agent` on it. Everything the router adds on the way
through — most visibly the hot-resume steer message — is invisible to a caller
that constructs `LocalEnv()` itself and awaits `run_agent` directly. That
bypass compiles, runs, and produces a plausible result with the steer silently
dropped, which is the failure mode this exists to stop.

The rule was applied 279 times and failed 65, the highest traffic of its
batch, because its condition fired on nearly every pipeline commit. No verdict
line in any snapshot records what was actually checked.

Its own body already proposed a grep — `RunPodEnv\(|LocalEnv\(|\.run_agent\(`
with the router path excluded. The checker exists because that grep names
three things the tree is free to rename.

## Mechanism

Everything the grep would hard-code is derived instead.

| what a grep names | how it is derived |
|---|---|
| the env classes | fixpoint over base chains, whole tree |
| the gated method | abstract public methods of the interface |
| the door | the guarded module with the most sites |

The implementation set resolves to `ExecuteEnv`, `LocalEnv`, `RunPodEnv` with
none of them written down — including `RunPodEnv`, which is only ever imported
lazily inside a function body. The gated method is read off the interface
class's own AST, so a rename follows automatically. The door is the guarded
module that both constructs an implementation and calls a gated method most
often; move or rename the router and nothing here needs editing, while a tie
for busiest is reported as an ambiguous chokepoint rather than picked.

| bad diff | mechanism |
|---|---|
| a new executor awaits `run_agent` | gated call outside the door |
| a new executor builds its own env | construction outside the door |
| a second router grows | a gated module that is not the door |
| the router moves, a path ban dies | door by weight; exit 2 if none |
| a module that does not parse | reported, never skipped |

**The interface library is deliberately not guarded.** The rule's own
independent verification found `aii_lib/src/aii_lib/execute_env/__init__.py`
opens with a docstring instructing the opposite — construct directly, then
await `run_agent` — so a blanket ban would contradict the library's published
contract. `CONFIG["guarded_roots"]` is `aii_pipeline/src` alone, and a test
pins that the interface package stays outside.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**0 findings**, whole-tree runtime **0.22 s** (three runs). 187 guarded
modules scanned; exactly one holds a gated site, and it is the router — 88 and
83 construct `LocalEnv`/`RunPodEnv`, lines 112 and 138 call `run_agent`.

Because stock is 0, the hook ships in its whole-tree form with no
`{staged_files}`: a bypass introduced by a file the glob misses still blocks,
and there is no debt to carry. The glob only decides when it runs.

The whole-tree class census is a `class Name(Bases)` regex rather than an
`ast.parse` of 1500 files — safe because only names matter at that step, and
every structural decision downstream still comes from the AST. That is the
difference between 0.83 s and 0.22 s.

## Fragility

| refactor | effect | guard |
|---|---|---|
| interface package moves | nothing derivable | exit 2, names key |
| the last impl is renamed out | nothing to funnel | exit 2 |
| the router stops calling | ban matches nothing | exit 2, moved |
| guarded roots move | no files | exit 2 |
| a bypass outgrows the router | door would flip | tie reported only |
| the interface gains a method | ban widens | intended; knob |

The door-flip case is the honest gap: a tie is reported, but a bypass holding
a strict majority of gated sites would be elected the door. That needs a
bypass with five or more sites in one module, which is a rewrite rather than a
slip. `CONFIG["ignored_methods"]` exists for generic interface names; a
genuinely new API method on `ExecuteEnv` should be funnelled, so widening
there is the intent rather than a defect.

## Residue

None material — the invariant is fully mechanical.

What the checker does not cover is the rest of the family. This is the
generic CLASS-SHAPED member of the 30 one-door rules: nothing in it mentions
agents or execution, so another interface package and another guarded root
enforce any "one interface, one entry point" invariant whose funnel is a class
hierarchy. The function-shaped members — a funnel to a free function, or a ban
on bare `write_text` — need a sibling with the same door derivation and the
same vacuity guards over a function-name universe. Worth building once rather
than thirty times.
