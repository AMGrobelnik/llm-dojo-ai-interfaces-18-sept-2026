# Every UI primitive ships a co-located story that imports it

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

Stories are the frontend regression surface here: `vitest-sb-fe` runs them as
tests, and commit `2231f9fa9` made story collection itself gated. A primitive
with no story sits outside the only harness that renders it on its own. The
rule was filed on four primitives that had landed without one
(`confirm-dialog`, `info-tooltip`, `inline-rename-input`, `switch`); it was
evaluated 37 times to answer a question a shell loop answers.

Its own note is worth keeping: three of those four were already rendered
indirectly by `compute.stories.tsx` and `guided-setup.stories.tsx`, so a
co-located story is the cheap way to guarantee DIRECT cover, not the only way
to get any cover. The hook inherits that framing — a primitive without a
sibling story is untested ON ITS OWN, which is all it claims.

## Mechanism

Pairing over `git ls-files`, plus an import test the proposed `[ -f ]` loop
cannot do.

| failure mode | mechanism |
|---|---|
| a new primitive with no story | pairing by name over the index |
| a story that renders something else | must import `./<stem>` |
| the directory renamed | population floor, exit 2 |
| a peer's scratch `.tsx` on disk | population is `git ls-files` |
| a story unreadable from the index | reported, not a crash |

Two departures from the shell loop the rule body proposed. The population is
the index, not a disk glob, because in a shared checkout a glob resolves
whatever a concurrent agent has lying around and the verdict then depends on
someone else's scratch file. And the story must IMPORT its subject: an empty
or repointed `foo.stories.tsx` satisfies a filename pairing while rendering
nothing, which is the same decorative-gate shape the rule exists to close.

With paths the twin is derived from the changed path by name in both
directions, so a story rewritten to import something else is caught, and an
orphan elsewhere in the directory is not charged to this commit.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**0 findings**, exit 0. 14 tracked primitives under
`aii_frontend/components/ui/`, all 14 with a co-located story that imports
them. (The rule body's "15 of 15" is 14 of 14 today: `info-tooltip.tsx` was
renamed to `info-tip.tsx`.) Whole-tree runtime 0.04 s (0.04 / 0.03 / 0.04).

Proved to bite on the real files: seeded with the live `components/ui/`,
deleting `switch.stories.tsx` gives "no co-located switch.stories.tsx", and
restoring it with its import repointed at `./spinner` gives "story does not
import `switch`" — the second is the case a filename pairing waves through.

## Fragility

| refactor | effect | guard |
|---|---|---|
| `components/ui/` renamed | nothing found | floor of 8, exit 2 |
| primitives nested deeper | still found | the pathspec crosses `/` |
| the story suffix changes | pairing breaks | loud: all report |
| Storybook dropped | rule goes with it | `vitest-sb-fe` fails first |

## Residue

Import presence is a proxy for "the story renders it": a story that imports
the primitive and never mounts it still passes. Closing that needs the JSX
render graph, and the next layer already covers it — `vitest-sb-fe` RUNS the
stories, so a story that renders nothing fails there rather than here.
