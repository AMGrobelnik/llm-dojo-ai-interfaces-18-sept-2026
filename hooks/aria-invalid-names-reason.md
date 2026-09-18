<!-- hook: aria-invalid-names-reason -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A control that sets aria-invalid also wires aria-describedby to its visible reason — an invalid mark never ships with an orphaned error line.

This pins a repaired, measured defect class the external audit labeled F55:
features/auth/auth-shell.tsx:120-127 records the before-state ("measured on
/signup after an empty submit, both inputs had aria-invalid=true and aria-
describedby=null, so a screen reader announced 'invalid entry' and never the
reason") and features/run-config/sections/api-keys.tsx:220-236 records the
same gap repaired with mutually-exclusive describedby targets. Both current
aria-invalid sites conform — the rule is green today and keeps the third form
field honest. Both citations re-measured 2026-09-06 with
`grep -n 'aria-invalid\|aria-describedby' <file>`: auth-shell is exact
(`aria-invalid` at :120, `aria-describedby` at :127), api-keys had drifted
from the recorded :271-287 to :220-236 (`aria-invalid` at :220, the
`aria-describedby` ternary spanning :230-236). Distinct from
rule-icon-controls-named (accessible names on icon controls, not
invalid-reason wiring).

Type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: fe-a11y-ux)

## ADOPTED 2026-09-06 — presence-pairing per FILE, and the pathspec matters

`metadata.command` carries the proposal's shape — every file that sets
`aria-invalid={…}` must also mention `aria-describedby` — with three changes.
Both halves ask the INDEX — `git grep --cached -l` for the file list and
`git grep --cached -q` for the pairing — rather than `grep -rl` and a disk
read, so neither an untracked file nor a peer's unstaged edit can decide the
verdict (re-probed through a scratch index of this repo: a staged orphan
exits 1 naming it, HEAD alone exits 0); the offenders are collected
and PRINTED instead of `exit 1` in silence; and stories are dropped by the
`:!*.stories.tsx` pathspec rather than a `grep -v` on the path.

**The pathspec is the part that had to be measured.** Written the obvious way,
`'aii_frontend/app/**/*.tsx'`, it silently sees LESS than the directory it
names: git's default pathspec matching has `*` cross `/` while the literal `/`
in `**/` must still be present, so a file sitting directly in the directory is
never matched — 32 files against 39 for `aii_frontend/app/*.tsx`, measured
2026-09-06. A probe caught it: an orphaned `aria-invalid` planted directly in
`components/` passed. The adopted pathspecs are the single-`*` form.

This is a per-FILE presence check, which is what the third filter verdict
below asks a parser for and does not get: a file that pairs the attributes on
DIFFERENT elements passes. It catches the F55 before-state (no `describedby`
anywhere in the file) and nothing finer.

Proven to bite 2026-09-06, in a throwaway `git init` tree under the scratch
dir — never against the repo's own files:

| probe | exit |
|---|---|
| both attributes present, nested file | 0 |
| orphan sitting directly in `components/` | 1, the file named |
| `aria-invalid` alone, nested file | 1, the file named |
| the same in a nested `.stories.tsx` | 0 — excluded |
| the same in a top-level `.stories.tsx` | 0 — excluded |

Delete-check: The real delete is folding every field into one primitive that pairs the two
attributes structurally — auth-shell's LabeledField already is that. But api-
keys' field is legitimately bespoke (two mutually-exclusive reason ids), so a
single primitive doesn't cover the tree; the rule enforces the pairing
wherever a bespoke field remains and collapses to a one-file check if the
fields ever unify.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Pins a repaired, measured defect class (F55: aria-invalid with
orphaned error line) that oxlint's jsx_a11y set does not cover (aria-props
checks attribute validity, not pairing). No claimed rule touches it. Note the
LabeledField structural collapse as the eventual delete.
- KILL: Pairing detection is brittle statically (attributes computed, spread,
or set by primitives) so the cmd-check either over-fires or goes vacuous; the
repaired sites are pinned by prose+story, its own delete-check names the real
fix (shared LabeledField primitive), and flow-axe-serious-zero covers the
adjacent describedby-resolution failures.
- KEEP: Keep, but the check must pair attributes within one JSX element via a
real parser (small oxc/ts-morph script), not line-proximity regex — cross-line
attributes and spreads defeat regex silently, which is the vacuity trap.
Static presence-pairing catches the F55 before-state (absent describedby).
