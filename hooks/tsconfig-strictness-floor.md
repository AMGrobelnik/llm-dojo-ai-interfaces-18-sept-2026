# The frontend typechecker config's strictness floor only ever goes up

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

`tsgo-fe` runs the typechecker, but with whatever the config says. Flipping
`strict` to false makes every violation pass while that gate stays green —
the decorative-gate failure `rule-lint-gates-actually-bite` closes on the
Python side and nothing closed on the frontend side. The condition fires only
when the config is touched, which is exactly right for a floor: it costs
nothing until someone edits the file, and then it is the only thing looking.

The rule already carried a one-line `jq` in its own body and was an agent
rule only because nobody minted it. That `jq` is weaker than it looks in four
separate ways, all of which the program closes.

## Mechanism

Two layers. The PINNED floor is a named list of flags that must be `true`
(and one that must be `false`), tested by identity rather than truthiness.
The POLARITY TABLE is TypeScript's own strict family: a flag nobody pinned,
written down at its loose value, is a finding — absence is a default,
presence at the loose value is a decision to be looser.

| failure mode | mechanism |
|---|---|
| a pinned flag flipped to false | `is not True`, per flag |
| a pinned flag deleted | membership test, not a default |
| `"strict": "yes"` | identity; the proposed `jq` passes it |
| `strictNullChecks: false` added | polarity table, 22 + 5 flags |
| `allowUnreachableCode` enabled | same table, other polarity |
| the floor moved into `extends` | reported, never silently trusted |
| the config renamed or deleted | nothing tracked matches, exit 2 |
| the pinned list edited to nothing | below `min_flags`, exit 2 |
| JSONC comments | stripped before parsing |

`jq -e` on a missing file exits 2 as well, but as "tooling broken" rather
than "the floor is gone"; here the vacuity exit carries a sentence saying the
config moved and that a missing config must never read as a satisfied floor.

## Stock

Measured against `/home/<user>/projects/research-monorepo` at HEAD `3f1060fa7`:
**0 findings**, exit 0. All ten pinned flags are `true`,
`allowUnusedLabels` is `false`, and no strict-family flag appears at a loose
value. Whole-tree runtime 0.02 s (three runs, all 0.02 s).

## Fragility

| refactor | effect | guard |
|---|---|---|
| the config renamed or moved | nothing to read | exit 2 |
| the pinned list cut down | floor is empty | `min_flags`, exit 2 |
| strictness moved to a base | unread | reported as a finding |
| a second, looser config | unchecked | widen CONFIG `pattern` |

The glob hands over any `tsconfig*.json`, but CONFIG's pattern matches only
the frontend one, so a new config elsewhere needs a one-line widening.

## Residue

None the rule claimed. The hook pins declared values; whether the typechecker
was actually RUN is `tsgo-fe`'s job, and the two are complementary — that one
proves the check ran, this one proves it still checks something.
`skipLibCheck` and `allowJs` are deliberately unpinned: both are pre-existing
relaxations in the live file, so pinning them would have started the hook red
for no gain.
