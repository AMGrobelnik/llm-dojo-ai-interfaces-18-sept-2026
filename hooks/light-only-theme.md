<!-- hook: light-only-theme -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# The app stays light-only: zero dark: utilities, no .dark token block, color-scheme light declared

`app/globals.css:186-197` states the invariant in prose — "The app is
light-only (there is no ``.dark`` token block and zero ``dark:`` utilities)" —
and `color-scheme: light` at `:198` exists specifically to stop dark-OS mobile
browsers rendering native form-control internals, autofill backgrounds and
default scrollbars in dark colours against the app's white cards. Measured
2026-09-05: zero real `dark:` utilities across `app/`, `features/` and
`components/`, no `.dark` token block, and the `@custom-variant dark` hook is
GONE — removed by `9c6976f77` (2026-09-03), with `:192-197` now recording in
past tense why it went. While the hook was there, any pasted shadcn snippet
carrying `dark:` classes compiled into real utilities that no applied `.dark`
class could ever activate: dead CSS invisible to `fallow` (which analyzes
exports, not class strings) and to every reviewer testing on a light theme.

Type: **cmd-check** · scope: **whole-tree** · value: **low** (proposer: frontend-config)

## ADOPTED 2026-09-06 — the anchored command is in the frontmatter

`metadata.command` now carries the three halves, so the invariant blocks in
both lanes instead of asking an agent to look. One change against the
proposal: each `grep` half prints its own diagnostic. `&& ! grep -q …` exits 1
with NO stdout when it fires — the silent shape the section below names, and
the one `rule-one-help-tip` had to repair at its own adoption — so the
inversion is written as an `if` with a `BLOCKED:` line. `rules-grep` prints
its own hits, and `|| exit` forwards its status unchanged, so a usage error
(exit 2) stays infrastructure instead of being downgraded to a block.

Both `globals.css` halves read the INDEX — `git grep --cached … --
aii_frontend/app/globals.css` — as `rules-grep --tree` does since
3c0448b05: a peer's unstaged edit to that file is not this commit's to answer for,
and a staged deletion of the `color-scheme` line is judged even while the
disk copy still carries it. Re-probed through a scratch index of this repo
(`GIT_INDEX_FILE`, `read-tree HEAD`, a blob staged with `update-index
--cacheinfo`, the working tree untouched): a staged `dark:bg-black` exits 1
naming the file, a staged `@custom-variant dark` line and a staged removal of
`color-scheme: light` each exit 1 with their `BLOCKED:` line, HEAD alone
exits 0.

Re-probed 2026-09-06 against the adopted text, in the same shape of throwaway
`git init` tree and over the same six mutations as the table below: identical
verdicts, and each blocking one now names its cause — `BLOCKED: globals.css
carries a dark variant hook or a .dark token block` for the two `globals.css`
residue rows, `BLOCKED: globals.css no longer declares color-scheme: light`
for the `color-scheme` row, and the offending line itself for the two
`dark:` rows.

## The pattern is ANCHORED, because the unanchored form self-trips (2026-09-05)

The command carried `'\bdark:'` and `'@custom-variant dark'` unanchored until
today. Both matched the FILE THAT DOCUMENTS THE INVARIANT, so adopting it as
written would have blocked every commit on the prose that explains the rule:

| pattern | self-trip |
|---|---|
| `\bdark:` | `globals.css:187`, `:194` — two prose lines |
| `@custom-variant dark` | `globals.css:192` — the removal note |

Measured: the full unanchored command with `--tree` exits **1** on today's
clean tree, printing the two `dark:` comment lines. The `@custom-variant` half
is worse — `! grep -q` prints NOTHING when it fires, so an adoption would have
blocked with no stdout and no hint why, the same silent shape
`rule-one-help-tip` had to fix in its own absence check.

Anchoring, not excluding the file, is the right instrument. Excluding
`globals.css` from the `dark:` scan would blind the rule to `@apply dark:…`,
which is exactly where a CSS-side dark utility would appear; and the `.dark`
clause has to read that file. So:

* `\bdark:[a-z[]` — a real utility is `dark:` followed by a class name or by
  `[` for an arbitrary variant. The prose writes ``` ``dark:`` ```, i.e. a
  backtick, which is neither.
* `^\s*@custom-variant dark` — the residue is a top-level at-rule at column 0;
  the comment line begins with spaces and a `*`.

Both anchored halves were probed 2026-09-05 in a throwaway `git init` tree
holding a copy of the real `globals.css` — never against the repo's own files:

| probe | exit |
|---|---|
| today's tree, unmodified | 0 |
| `className="… dark:bg-black"` | 1 |
| `className="dark:[&_svg]:text-white"` | 1 |
| `@custom-variant dark` back at column 0 | 1 |
| a `.dark { … }` token block appended | 1 |
| `color-scheme: light` changed to `dark` | 1 |

Delete-check: This rule enforces a deletion end-state, and the deletion is
already complete: dark mode was the deleted dimension and the leftover
`@custom-variant dark` hook — the one thing this rule used to require removing
at adoption — went with `9c6976f77`. Nothing is left to delete, so the rule is
now a pure zero-state pin. If dark mode is ever deliberately rebuilt, the rule
is deleted in that same commit, which is precisely the visibility a silent
one-off `dark:` utility lacks today.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Enforces a completed deletion (dark mode) whose residue line should go
at adoption; a single dark: utility creeping in renders unstyled against light
tokens. Zero-offender grep, trivial cost.
- KEEP: Stated invariant with a real rendering consequence (dark-OS form
controls on white cards); zero dark: utilities today so the grep is a free
pin, and it flushes the leftover @custom-variant residue.
- KEEP: Three-line check: zero 'dark:' occurrences, no .dark block, color-
scheme light present — plus delete the residual @custom-variant line at
adoption. Near-zero cost, loud.

PORTED 2026-09-14 onto the one-pass AST dispatcher: `run.sh` and its
standalone `amg-hooks-grep`/`git grep` command are removed, `light-only-theme` is
removed from `research-monorepo/lefthook.yml`, and `research-monorepo-ast-checks` (the
shared dispatcher command) now discovers and runs `dispatch.py` in the same
pass as every other TypeScript AST-confirmed hook. `SCOPE` is `"tree"`,
matching the retired `--tree` / `--cached` reads: there is one lane, and a
committed violation blocks a later unrelated commit the same as any other
tree-mode hook.

The `dark:` half keeps `amg-hooks-grep`'s anchored ERE (`\bdark:[a-z[]`) as a
line-level candidate prefilter and adds a `tsast` confirmation the bare regex
never had: a candidate survives only if it sits inside a real
`StringLiteral`/template span, so a `//` or `/* */` comment naming the utility
(the exact shape this README's own history section records tripping the
UNANCHORED form of this pattern) is dropped rather than counted, the same
predicate `color-tokens` already carries for its own Tailwind class-name ban.
The two `globals.css` checks — the residue at column 0 and the presence of
`color-scheme: light` — have no comment/string ambiguity to resolve (CSS is
not a grammar `tsast` parses), so they stay direct literal checks over the
same `Services`-supplied INDEX text.

Measured 2026-09-14 against the real research-monorepo index (`AMG_HOOKS_SWEEP=1`): the
`dark:` half's candidate population is 0 (`grep -rnE '\bdark:[a-z[]'
aii_frontend/app aii_frontend/features aii_frontend/components` -> 0 hits),
0 AST findings, ADDED 0; `globals.css:198` still declares `color-scheme:
light` and carries no residue line, so both direct checks are clean too. The
dispatcher run over the whole tree agrees: `light-only-theme=0`.

## History

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. It confirmed
the prose block, `color-scheme: light`, the absence of a `.dark` token block and
zero `dark:` utilities in TSX, and it found the mechanism half wrong: `.dark`
was applied at `app/layout.tsx:48`, arming any pasted `dark:` utility.

Re-measured 2026-08-28, that defect was already gone (`grep -n dark
app/layout.tsx` returns nothing, still true today, exit 1), leaving one line of
residue — `@custom-variant dark` at `globals.css:5`. The body then said the
command "arrives RED on that line alone" and that deleting it was the adopting
commit's one frontend edit.

Every coordinate in those two rounds has since drifted: the prose block moved
from `:88-92` to `:186-197`, `color-scheme: light` from `:93` to `:198`, and
the residue at `:5` no longer exists. The command arrives RED for a different
reason now — its own unanchored patterns — which is what the section above
fixes.
